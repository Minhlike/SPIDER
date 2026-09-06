package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func reply(status int, body string) *http.Response {
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}
}

func TestParentPermitPrecedesNetworkAndDenialSendsNothing(t *testing.T) {
	for _, allowed := range []bool{false, true} {
		asked, sent := false, 0
		g := &guardedTransport{host: "api.shodan.io", maxRequests: 1,
			permit: func(entry requestJournalEntry) bool {
				if sent != 0 || entry.Sequence != 1 || entry.Destination != "api.shodan.io" {
					t.Fatal("permit did not precede transport")
				}
				asked = true
				return allowed
			}, base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
				if !asked {
					t.Fatal("network without permit")
				}
				sent++
				return reply(200, `{"plan":"dev"}`), nil
			})}
		req, _ := http.NewRequest("GET", "https://api.shodan.io/api-info", nil)
		_, _ = g.RoundTrip(req)
		want := 0
		if allowed {
			want = 1
		}
		if !asked || sent != want || g.requests != want || len(g.journal) != want {
			t.Fatal("incorrect permit/request accounting")
		}
	}
}

func TestClassification(t *testing.T) {
	for _, test := range []struct {
		status      int
		body, state string
	}{
		{200, `{"plan":"dev","query_credits":10}`, valid}, {401, `{"error":"key"}`, invalid},
		{403, `{"error":"Invalid API key"}`, invalid}, {403, `{"error":"Access denied"}`, limited},
		{429, `{}`, limited}, {402, `{}`, limited}, {503, `{}`, network},
		{200, `<html>Login</html>`, network}, {200, `{"error":true,"errmsg":"invalid api key"}`, invalid},
		{200, `{"error":true,"errmsg":"insufficient credits"}`, limited},
		{200, `{"error":true,"errmsg":"unknown upstream error"}`, network},
	} {
		state, _ := classify(test.status, []byte(test.body))
		if state != test.state {
			t.Errorf("wrong classification for HTTP %d", test.status)
		}
	}
}

func TestTLSAndDestinationBoundaries(t *testing.T) {
	called := 0
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { called++; w.Write([]byte(`{}`)) }))
	defer server.Close()
	parsed, _ := url.Parse(server.URL)
	g := &guardedTransport{base: secureBase(), host: parsed.Host, maxRequests: 1}
	req, _ := http.NewRequest("GET", server.URL, nil)
	if _, err := secureClient(g).Do(req); err == nil || called != 0 {
		t.Fatal("untrusted TLS certificate accepted")
	}
	g.host = hosts["shodan"]
	if _, err := g.RoundTrip(req); err == nil {
		t.Fatal("foreign destination accepted")
	}
	req.URL.Scheme = "http"
	if _, err := g.RoundTrip(req); err == nil {
		t.Fatal("plaintext transport accepted")
	}
	if secureBase().Proxy != nil || secureBase().TLSClientConfig.InsecureSkipVerify {
		t.Fatal("unsafe transport defaults")
	}
}

func TestRedirectsAndBodyLimit(t *testing.T) {
	calls := 0
	g := &guardedTransport{host: hosts["shodan"], maxRequests: 1, base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		response := reply(302, `{}`)
		response.Header.Set("Location", "https://untrusted.invalid/")
		return response, nil
	})}
	response, err := secureClient(g).Get("https://api.shodan.io/api-info?key=synthetic")
	if err != nil || response.StatusCode != 302 || calls != 1 {
		t.Fatal("redirect was followed")
	}
	g.requests = 0
	g.base = roundTripFunc(func(r *http.Request) (*http.Response, error) { return reply(200, strings.Repeat("x", maxBody+1)), nil })
	if _, err := secureClient(g).Get("https://api.shodan.io/api-info"); err == nil {
		t.Fatal("unbounded body")
	}
}

func TestRequestJournalContainsNoURLQueryOrCredential(t *testing.T) {
	secret := "synthetic-secret-that-must-not-escape"
	g := &guardedTransport{host: hosts["shodan"], purpose: "account_validation", maxRequests: 1,
		base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
			return reply(200, `{"plan":"dev","query_credits":5}`), nil
		})}
	response, err := secureClient(g).Get("https://api.shodan.io/api-info?key=" + secret)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if len(g.journal) != 1 {
		t.Fatal("journal must contain exactly one network dispatch")
	}
	entry := g.journal[0]
	if entry.Sequence != 1 || entry.Method != "GET" || entry.Destination != hosts["shodan"] ||
		entry.Purpose != "account_validation" || entry.HTTPStatus != 200 || entry.Outcome != "HTTP_200" {
		t.Fatal("incorrect request journal", entry)
	}
	encoded, _ := json.Marshal(g.journal)
	if strings.Contains(string(encoded), secret) || strings.Contains(string(encoded), "api-info") ||
		strings.Contains(string(encoded), "key=") {
		t.Fatal("journal exposed request details")
	}
}

func TestRequestJournalRecordsFailedDispatch(t *testing.T) {
	g := &guardedTransport{host: hosts["fofa"], purpose: "internet_asset_search", maxRequests: 1,
		base: roundTripFunc(func(r *http.Request) (*http.Response, error) { return nil, errors.New("synthetic") })}
	req, _ := http.NewRequest("GET", "https://fofa.info/api/v1/search/all?key=synthetic", nil)
	if _, err := secureClient(g).Do(req); err == nil {
		t.Fatal("failure expected")
	}
	if len(g.journal) != 1 || g.journal[0].Outcome != "CONNECTION_FAILED" || g.journal[0].HTTPStatus != 0 {
		t.Fatal("failed dispatch not journaled")
	}
}

func TestAccountsAndSearchScope(t *testing.T) {
	for _, engine := range []string{"shodan", "censys", "fofa"} {
		keys := map[string]string{"SHODAN_API_KEY": "fake-shodan", "CENSYS_API_TOKEN": "fake-censys", "CENSYS_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000001", "FOFA_EMAIL": "test@example.invalid", "FOFA_KEY": "fake-fofa"}
		body := map[string]string{"shodan": `{"plan":"dev","query_credits":5}`, "censys": `{"result":{"balance":5}}`, "fofa": `{"error":false,"email":"test@example.invalid"}`}[engine]
		g := &guardedTransport{host: hosts[engine], maxRequests: 1, base: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			if engine == "censys" && req.Header.Get("Authorization") != "Bearer fake-censys" {
				t.Fatal("missing bearer")
			}
			return reply(200, body), nil
		})}
		state, reason, warning := accountCheck(context.Background(), engine, keys, secureClient(g))
		expected := map[string]string{"shodan": valid, "censys": validFree, "fofa": keyValid}[engine]
		if state != expected || warning != "" {
			t.Fatal("incorrect account scope", engine, state, reason)
		}
		g.requests = 0
		g.base = roundTripFunc(func(req *http.Request) (*http.Response, error) { return reply(200, `{}`), nil })
		state, _, _ = accountCheck(context.Background(), engine, keys, secureClient(g))
		if state != network {
			t.Fatal("invalid schema accepted")
		}
	}
}

func TestPinnedAgentsReceiveExpectedSchema(t *testing.T) {
	for _, engine := range []string{"shodan", "censys", "fofa"} {
		keys := map[string]string{"SHODAN_API_KEY": "fake-shodan", "CENSYS_API_TOKEN": "fake-censys", "CENSYS_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000001", "FOFA_EMAIL": "test@example.invalid", "FOFA_KEY": "fake-fofa"}
		g := &guardedTransport{host: hosts[engine], maxRequests: 1, base: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			switch engine {
			case "shodan":
				if req.URL.Query().Get("key") != keys["SHODAN_API_KEY"] {
					t.Fatal("Shodan key not injected")
				}
				return reply(200, `{"matches":[],"total":0}`), nil
			case "fofa":
				if req.URL.Query().Get("key") != keys["FOFA_KEY"] || req.URL.Query().Get("size") != "1" {
					t.Fatal("FOFA config mismatch")
				}
				return reply(200, `{"error":false,"results":[],"size":0}`), nil
			default:
				if req.Header.Get("Authorization") != "Bearer fake-censys" {
					t.Fatal("Censys bearer missing")
				}
				if req.URL.Query().Get("organization_id") != keys["CENSYS_ORGANIZATION_ID"] && req.Header.Get("X-Organization-ID") != keys["CENSYS_ORGANIZATION_ID"] {
					t.Fatal("Censys organization missing")
				}
				return reply(200, `{"result":{"hits":[],"next_page_token":""}}`), nil
			}
		})}
		report := search(context.Background(), engine, "example.invalid", 1, keys, g)
		if report.State != valid || g.requests != 1 {
			t.Fatal("pinned agent failed", engine, report.State, report.Reason, g.requests)
		}
		encoded, _ := json.Marshal(report)
		if strings.Contains(string(encoded), "fake-") {
			t.Fatal("credential leaked")
		}
	}
}

func TestCensysFreeTokenAndFOFAKeyOnly(t *testing.T) {
	keys := map[string]string{"CENSYS_API_TOKEN": "free-token", "FOFA_KEY": "key-only"}
	g := &guardedTransport{host: hosts["censys"], maxRequests: 1, base: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.URL.Path != "/v3/accounts/users/credits" || req.Header.Get("X-Organization-ID") != "" {
			t.Fatal("free token requested an organization")
		}
		return reply(200, `{"result":{"balance":0}}`), nil
	})}
	state, _, _ := accountCheck(context.Background(), "censys", keys, secureClient(g))
	if state != validFree {
		t.Fatal("free account token was not accepted")
	}
	g.requests = 0
	g.base = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Method != "POST" || req.Header.Get("X-Organization-ID") != "" {
			t.Fatal("token-only search config wrong")
		}
		return reply(403, `{"error":"free plan"}`), nil
	})
	searchResult := search(context.Background(), "censys", "example.invalid", 1, keys, g)
	if searchResult.State != noSearch {
		t.Fatal("free entitlement classified incorrectly")
	}

	fofaKeys := map[string]string{"FOFA_KEY": "key-only", "FOFA_EMAIL": "legacy@example.invalid"}
	g = &guardedTransport{host: hosts["fofa"], maxRequests: 1, base: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return reply(200, `{"error":false,"email":"account@example.invalid"}`), nil
	})}
	state, _, warning := accountCheck(context.Background(), "fofa", fofaKeys, secureClient(g))
	if state != keyValid || warning != "ACCOUNT_EMAIL_MISMATCH" {
		t.Fatal("FOFA email mismatch invalidated a valid key")
	}
}

func TestProviderSpecificFailureStates(t *testing.T) {
	if providerState("censys", "account", network, 401) != invalidToken {
		t.Fatal("censys invalid token")
	}
	if providerState("censys", "search", limited, 403) != noSearch {
		t.Fatal("censys entitlement")
	}
	if providerState("censys", "search", limited, 429) != rate {
		t.Fatal("censys rate")
	}
	if providerState("censys", "search", limited, 402) != quota {
		t.Fatal("censys quota")
	}
	if providerState("fofa", "account", invalid, 200) != invalidKey {
		t.Fatal("fofa invalid key")
	}
	if providerState("fofa", "search", limited, 403) != noQuery {
		t.Fatal("fofa entitlement")
	}
	if providerState("fofa", "search", limited, 429) != rate {
		t.Fatal("fofa rate")
	}
	if providerState("fofa", "search", limited, 402) != quota {
		t.Fatal("fofa quota")
	}
}
