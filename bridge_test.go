package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestEngineReadIntegration(t *testing.T) {
	engine := os.Getenv("ENGINE_TEST_URL")
	if engine == "" {
		t.Skip("ENGINE_TEST_URL not provided")
	}
	a, _ := testApp(t)
	a.cfg.Engine = engine
	c, csrf := login(t, a)
	for _, op := range []string{"library", "history", "downloads", "repositories"} {
		w := request(a, "POST", "/api/bridge", `{"operation":"`+op+`","variables":{}}`, c, "", csrf)
		var out struct {
			Data   map[string]any `json:"data"`
			Errors []any          `json:"errors"`
		}
		if w.Code != 200 || json.Unmarshal(w.Body.Bytes(), &out) != nil || len(out.Errors) > 0 || out.Data == nil {
			t.Errorf("%s: HTTP %d %s", op, w.Code, w.Body.String())
		}
	}
}
func TestCuratedGraphQLBridge(t *testing.T) {
	calls := 0
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Method != "POST" || r.URL.Path != "/api/graphql" || r.Header.Get("Cookie") != "" || r.Header.Get("X-CSRF-Token") != "" {
			t.Errorf("invalid bridge upstream %s %s", r.Method, r.URL)
		}
		var payload struct {
			Query     string         `json:"query"`
			Variables map[string]any `json:"variables"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		if payload.Query == "" || strings.Contains(payload.Query, "setSettings") {
			t.Error("unsafe query")
		}
		w.Header().Set("Set-Cookie", "engine=secret")
		_, _ = w.Write([]byte(`{"data":{"ok":true}}`))
	}))
	defer up.Close()
	a, _ := testApp(t)
	a.cfg.Engine = up.URL
	c, csrf := login(t, a)
	for _, op := range []string{"library", "history", "downloads", "repositories"} {
		w := request(a, "POST", "/api/bridge", `{"operation":"`+op+`","variables":{}}`, c, "", csrf)
		if w.Code != 200 || !strings.Contains(w.Body.String(), `"data"`) || w.Header().Get("Set-Cookie") != "" {
			t.Fatalf("bridge %s %d %s", op, w.Code, w.Body.String())
		}
	}
	for _, b := range []string{`{"operation":"settings"}`, `{"operation":"library","query":"query{settings{}}"}`, `{"operation":"library","variables":{"query":"x"}}`, `{"operation":"removeRepository","variables":{"indexUrl":"http://localhost/index.json"}}`} {
		w := request(a, "POST", "/api/bridge", b, c, "", csrf)
		if w.Code != 400 {
			t.Fatalf("unsafe bridge accepted %s: %d", b, w.Code)
		}
	}
	if w := request(a, "POST", "/api/bridge", `{"operation":"library"}`, c, "", ""); w.Code != 403 {
		t.Fatal("read bridge missing csrf")
	}
	if calls != 4 {
		t.Fatal("invalid request reached upstream", calls)
	}
}
