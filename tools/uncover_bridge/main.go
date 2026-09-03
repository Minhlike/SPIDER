// Private process boundary for Uncover v1.2.1. Never load/write provider YAML.
package main

import (
 "bytes"
 "context"
 "crypto/tls"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "log"
 "net/http"
 "net/url"
 "os"
 "strings"
 "time"

 "github.com/projectdiscovery/uncover/sources"
 "github.com/projectdiscovery/uncover/sources/agent/censys"
 "github.com/projectdiscovery/uncover/sources/agent/fofa"
 "github.com/projectdiscovery/uncover/sources/agent/shodan"
)

const version = "spider-uncover/v1.2.1-secure1"
const valid = "VALID"
const missing = "MISSING_CREDENTIAL"
const invalid = "INVALID_CREDENTIAL"
const limited = "PLAN/QUOTA_LIMIT"
const network = "NETWORK_ERROR"
const validFree = "VALID_FREE_PLAN"
const invalidToken = "INVALID_TOKEN"
const noSearch = "NO_SEARCH_ENTITLEMENT"
const quota = "QUOTA_LIMIT"
const rate = "RATE_LIMIT"
const keyValid = "KEY_VALID"
const noQuery = "NO_QUERY_ENTITLEMENT"
const invalidKey = "INVALID_KEY"
const maxBody = 2 * 1024 * 1024

var fields = map[string][]string{
 "shodan": {"SHODAN_API_KEY"},
 "censys": {"CENSYS_API_TOKEN"},
 "fofa": {"FOFA_KEY"},
}
var hosts = map[string]string{"shodan":"api.shodan.io", "censys":"api.platform.censys.io", "fofa":"fofa.info"}

type report struct {
 Engine string `json:"engine"`
 State string `json:"state"`
 Reason string `json:"reason"`
 Scope string `json:"scope"`
 HTTPStatus int `json:"http_status,omitempty"`
 Results []map[string]any `json:"results"`
 Warning string `json:"warning,omitempty"`
}

func providerState(engine, scope, state string, status int) string {
 if engine == "censys" {
  if status == 401 { return invalidToken }
  if status == 429 { return rate }
  if scope == "search" {
   if status == 403 { return noSearch }
   if status == 402 || state == limited { return quota }
  }
 }
 if engine == "fofa" {
  if state == invalid { return invalidKey }
  if status == 429 { return rate }
  if scope == "search" {
   if status == 403 { return noQuery }
   if status == 402 || state == limited { return quota }
  }
 }
 return state
}

func classify(status int, body []byte) (string, string) {
 // Only fixed labels leave this process. Provider bodies/URLs/errors never do.
 var data map[string]any
 _ = json.Unmarshal(body, &data)
 text := strings.ToLower(fmt.Sprint(data["error"], " ", data["errmsg"], " ", data["message"]))
 if status == 401 { return invalid, "AUTH_REJECTED" }
 if status == 402 || status == 429 { return limited, "PLAN_OR_QUOTA" }
 for _, phrase := range []string{"invalid api key", "invalid key", "invalid token", "unauthorized", "key is invalid", "key无效", "key错误", "账号或者key不正确"} {
  if strings.Contains(text, phrase) { return invalid, "AUTH_REJECTED" }
 }
 if status == 403 { return limited, "PERMISSION_DENIED" }
 for _, phrase := range []string{"quota", "credit", "limit exceeded", "insufficient", "subscription", "upgrade your", "会员", "积分", "配额", "余额", "次数", "没有权限"} {
  if strings.Contains(text, phrase) { return limited, "PLAN_OR_QUOTA" }
 }
 if status < 200 || status >= 300 { return network, "HTTP_ERROR" }
 if data == nil { return network, "UNEXPECTED_RESPONSE" }
 if value, ok := data["error"]; ok && value != false && value != nil && value != "" {
  return network, "PROVIDER_ERROR_UNCLASSIFIED"
 }
 return valid, "REQUEST_ACCEPTED"
}

type guardedTransport struct {
 base http.RoundTripper
 host string
 state, reason string
 status int
 requests, maxRequests int
}

func secureBase() *http.Transport {
 return &http.Transport{TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12},
  Proxy: nil, ResponseHeaderTimeout: 12*time.Second, TLSHandshakeTimeout: 10*time.Second}
}

func (g *guardedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
 if req.URL.Scheme != "https" || req.URL.Host != g.host || req.URL.User != nil {
  g.state, g.reason = network, "DESTINATION_BLOCKED"
  return nil, errors.New("destination blocked")
 }
 if g.requests >= g.maxRequests {
  if g.state == valid { g.reason = "PAGE_LIMIT" }
  return nil, errors.New("request budget reached")
 }
 g.requests++
 response, err := g.base.RoundTrip(req)
 if err != nil {
  g.state, g.reason = network, "CONNECTION_FAILED"
  return nil, errors.New("connection failed")
 }
 g.status = response.StatusCode
 body, err := io.ReadAll(io.LimitReader(response.Body, maxBody+1))
 response.Body.Close()
 if err != nil || len(body) > maxBody {
  g.state, g.reason = network, "UNEXPECTED_RESPONSE"
  return nil, errors.New("invalid response")
 }
 g.state, g.reason = classify(response.StatusCode, body)
 if g.state == valid && strings.Contains(req.URL.Path, "/search/") && !validSearchBody(req.URL.Host, body) {
  g.state, g.reason = network, "UNEXPECTED_RESPONSE"
  return nil, errors.New("invalid search response")
 }
 response.Body = io.NopCloser(bytes.NewReader(body))
 return response, nil
}

func validSearchBody(host string, body []byte) bool {
 var data map[string]any
 if json.Unmarshal(body, &data) != nil { return false }
 switch host {
 case hosts["shodan"]:
  rows, ok := data["matches"].([]any)
  _, totalOK := data["total"].(float64)
  if !ok || !totalOK { return false }
  for _, value := range rows {
   row, ok := value.(map[string]any); if !ok { return false }
   if ip, exists := row["ip_str"]; exists { if _, ok := ip.(string); !ok { return false } }
   if port, exists := row["port"]; exists { if _, ok := port.(float64); !ok { return false } }
  }
 case hosts["fofa"]:
  rows, ok := data["results"].([]any)
  if !ok || data["error"] != false { return false }
  for _, value := range rows {
   row, ok := value.([]any); if !ok || len(row) < 3 { return false }
   for _, column := range row[:3] { if _, ok := column.(string); !ok { return false } }
  }
 case hosts["censys"]:
  result, ok := data["result"].(map[string]any)
  if !ok { return false }
  if _, ok := result["hits"].([]any); !ok { return false }
 default: return false
 }
 return true
}

func validKeyFormat(engine string, keys map[string]string) bool {
 for _, value := range keys {
  if len(value) > 4096 || strings.ContainsAny(value, "\r\n\x00\t ") { return false }
 }
 switch engine {
 case "fofa":
  return !strings.ContainsAny(keys["FOFA_KEY"], "&?#%")
 default: return !strings.ContainsAny(keys["SHODAN_API_KEY"], "&?#%")
 }
}

func secureClient(g *guardedTransport) *http.Client {
 return &http.Client{Transport:g, Timeout:15*time.Second,
  CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
}

func accountCheck(ctx context.Context, engine string, keys map[string]string, client *http.Client) (string, string, string) {
 var address string
 switch engine {
 case "shodan": address = "https://api.shodan.io/api-info?" + url.Values{"key":{keys["SHODAN_API_KEY"]}}.Encode()
 case "censys": address = "https://api.platform.censys.io/v3/accounts/users/credits"
 case "fofa": address = "https://fofa.info/api/v1/info/my?" + url.Values{"key":{keys["FOFA_KEY"]}}.Encode()
 }
 req, err := http.NewRequestWithContext(ctx, "GET", address, nil)
 if err != nil { return invalid, "MALFORMED_CREDENTIAL", "" }
 req.Header.Set("Accept", "application/json")
 if engine == "censys" {
  req.Header.Set("Authorization", "Bearer " + keys["CENSYS_API_TOKEN"])
  if keys["CENSYS_ORGANIZATION_ID"] != "" { req.Header.Set("X-Organization-ID", keys["CENSYS_ORGANIZATION_ID"]) }
 }
 response, err := client.Do(req)
 if err != nil { return network, "CONNECTION_FAILED", "" }
 defer response.Body.Close()
 body, _ := io.ReadAll(response.Body)
 state, reason := classify(response.StatusCode, body)
 state = providerState(engine, "account", state, response.StatusCode)
 if state != valid { return state, reason, "" }
 var data map[string]any
 if json.Unmarshal(body, &data) != nil { return network, "UNEXPECTED_RESPONSE", "" }
 switch engine {
 case "shodan":
  _, planOK := data["plan"].(string)
  credits, creditsOK := data["query_credits"].(float64)
  if !planOK || !creditsOK { return network, "UNEXPECTED_RESPONSE", "" }
  limits, _ := data["usage_limits"].(map[string]any)
  if credits == 0 && limits["query_credits"] != float64(-1) { return limited, "NO_QUERY_CREDITS", "" }
 case "censys":
  result, _ := data["result"].(map[string]any)
  if _, ok := result["balance"].(float64); !ok { return network, "UNEXPECTED_RESPONSE", "" }
  return validFree, "ACCOUNT_VERIFIED", ""
 case "fofa":
  if data["error"] != false { return network, "UNEXPECTED_RESPONSE", "" }
  warning := ""
  if saved, ok := keys["FOFA_EMAIL"]; ok && saved != "" {
   if returned, ok := data["email"].(string); ok && !strings.EqualFold(returned, saved) { warning = "ACCOUNT_EMAIL_MISMATCH" }
  }
  return keyValid, "ACCOUNT_VERIFIED", warning
 }
 return valid, "ACCOUNT_VERIFIED_SEARCH_NOT_TESTED", ""
}

func censysTokenOnlySearch(ctx context.Context, query string, g *guardedTransport, keys map[string]string) report {
 result := report{Engine:"censys", State:network, Reason:"UNEXPECTED_RESPONSE", Scope:"search", Results:[]map[string]any{}}
 payload, _ := json.Marshal(map[string]any{"query":query, "page_size":1})
 request, err := http.NewRequestWithContext(ctx, http.MethodPost, "https://api.platform.censys.io/v3/global/search/query", bytes.NewReader(payload))
 if err != nil { return result }
 request.Header.Set("Authorization", "Bearer "+keys["CENSYS_API_TOKEN"])
 request.Header.Set("Content-Type", "application/json")
 request.Header.Set("Accept", "application/json")
 response, err := secureClient(g).Do(request)
 if err != nil { result.State, result.Reason, result.HTTPStatus = providerState("censys", "search", g.state, g.status), g.reason, g.status; return result }
 defer response.Body.Close()
 result.State, result.Reason, result.HTTPStatus = providerState("censys", "search", g.state, g.status), g.reason, g.status
 if result.State == valid { result.Reason = "SEARCH_VERIFIED" }
 return result
}

func search(ctx context.Context, engine, query string, limit int, keys map[string]string, g *guardedTransport) report {
 result := report{Engine:engine, State:network, Reason:"UNEXPECTED_RESPONSE", Scope:"search", Results:[]map[string]any{}}
 if engine == "censys" && keys["CENSYS_ORGANIZATION_ID"] == "" {
  return censysTokenOnlySearch(ctx, query, g, keys)
 }
 k := &sources.Keys{Shodan:keys["SHODAN_API_KEY"], CensysToken:keys["CENSYS_API_TOKEN"],
  CensysOrgId:keys["CENSYS_ORGANIZATION_ID"], FofaEmail:keys["FOFA_EMAIL"], FofaKey:keys["FOFA_KEY"]}
 if engine == "fofa" && k.FofaEmail == "" { k.FofaEmail = "uncover-compat@invalid.local" }
 session, err := sources.NewSession(k, 0, 15, 1, []string{engine}, time.Second, "")
 if err != nil { return result }
 // Replace the upstream insecure HTTP client BEFORE invoking any engine.
 session.Client.HTTPClient = secureClient(g)
 var agent sources.Agent
 switch engine {
 case "shodan": agent = &shodan.Agent{}
 case "censys": agent = &censys.Agent{}
 case "fofa": fofa.Size = limit; agent = &fofa.Agent{}
 }
 channel, err := agent.Query(ctx, session, &sources.Query{Query:query, Limit:limit})
 if err != nil { return result }
 for {
  select {
  case <-ctx.Done(): result.State, result.Reason = network, "TIMEOUT"; return result
  case item, ok := <-channel:
   if !ok {
    result.State, result.Reason, result.HTTPStatus = providerState(engine, "search", g.state, g.status), g.reason, g.status
    if result.State == valid { result.Reason = "SEARCH_VERIFIED" }
    return result
   }
   if item.Error != nil {
    result.State, result.Reason, result.HTTPStatus = providerState(engine, "search", g.state, g.status), g.reason, g.status
    if result.State == valid && result.Reason != "PAGE_LIMIT" { result.State, result.Reason = network, "UNEXPECTED_RESPONSE" }
    return result
   }
   row := map[string]any{"engine":engine, "ip":item.IP, "host":item.Host, "url":item.Url, "port":item.Port}
   encoded, _ := json.Marshal(row)
   leak := false
   for _, secret := range keys {
    if secret != "" && (bytes.Contains(encoded, []byte(secret)) || bytes.Contains(encoded, []byte(url.QueryEscape(secret)))) { leak = true }
   }
   if !leak { result.Results = append(result.Results, row) }
   if len(result.Results) >= limit {
    result.State, result.Reason, result.HTTPStatus = valid, "SEARCH_VERIFIED", g.status
    return result
   }
  }
 }
}

func main() {
 log.SetOutput(io.Discard)
 // flag diagnostics can contain arguments; discard them.
 flag.CommandLine.SetOutput(io.Discard)
 mode := flag.String("mode", "check", "check or search")
 engine := flag.String("engine", "", "engine")
 query := flag.String("q", "", "query")
 limit := flag.Int("limit", 10, "result limit")
 showVersion := flag.Bool("version", false, "version")
 flag.Parse()
 if *showVersion { fmt.Println(version); return }
 result := report{Engine:*engine, State:missing, Reason:"REQUIRED_FIELDS_MISSING", Scope:*mode, Results:[]map[string]any{}}
 required, ok := fields[*engine]
 if !ok || (*mode != "check" && *mode != "search") || *limit < 1 || *limit > 100 { os.Exit(2) }
 keys := map[string]string{}
 for _, field := range required {
  keys[field] = strings.TrimSpace(os.Getenv(field))
  os.Unsetenv(field)
  if keys[field] == "" { json.NewEncoder(os.Stdout).Encode(result); return }
 }
 if !validKeyFormat(*engine, keys) {
  result.State, result.Reason = invalid, "MALFORMED_CREDENTIAL"
  json.NewEncoder(os.Stdout).Encode(result); return
 }
 ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
 defer cancel()
 g := &guardedTransport{base:secureBase(), host:hosts[*engine], state:network, reason:"NOT_REQUESTED", maxRequests:1}
 if *mode == "check" {
  result.State, result.Reason, result.Warning = accountCheck(ctx, *engine, keys, secureClient(g))
  result.HTTPStatus = g.status
 } else { result = search(ctx, *engine, *query, *limit, keys, g) }
 json.NewEncoder(os.Stdout).Encode(result)
}
