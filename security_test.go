package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLegacyGETMutationsRequireCSRF(t *testing.T) {
	calls := 0
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(204) }))
	defer up.Close()
	a, _ := testApp(t)
	a.cfg.Engine = up.URL
	c, csrf := login(t, a)
	for _, p := range []string{"/api/v1/manga/42/library?inLibrary=true", "/api/v1/manga/42/category/1", "/api/v1/extension/install/pkg", "/api/v1/extension/update/pkg", "/api/v1/extension/uninstall/pkg", "/api/v1/downloads/start", "/api/v1/downloads/stop", "/api/v1/downloads/clear", "/api/v1/download/42/chapter/0", "/api/v1/source/12/filters?reset=true", "/api/v1/manga/42/chapter/0/page/0?updateProgress=true"} {
		w := request(a, "GET", p, "", c, "", "")
		if w.Code != 403 {
			t.Fatalf("unsafe GET accepted %s: %d", p, w.Code)
		}
		w = request(a, "GET", p, "", c, "", csrf)
		if w.Code != 204 {
			t.Fatalf("authorized GET %s: %d", p, w.Code)
		}
	}
	for _, p := range []string{"/api/v1/downloads", "/api/v1/chapter/42", "/api/v1/track/list", "/api/v1/manga/42/chapter/0/page/0?updateProgress=false"} {
		if w := request(a, "GET", p, "", c, "", ""); w.Code != 204 {
			t.Fatalf("read namespace %s: %d", p, w.Code)
		}
	}
	if calls != 15 {
		t.Fatal(calls)
	}
}
func TestLoginRateLimitUsesRemoteAddr(t *testing.T) {
	a, _ := testApp(t)
	for i := 0; i < 10; i++ {
		w := request(a, "POST", "/login", "username=admin&password=wrong", nil, "https://mg.example", "")
		if w.Code != 401 {
			t.Fatal(w.Code)
		}
	}
	r := httptest.NewRequest("POST", "/login", nil)
	r.Header.Set("Origin", "https://mg.example")
	r.Header.Set("X-Forwarded-For", "1.2.3.4")
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	if w.Code != 429 {
		t.Fatalf("XFF bypass %d", w.Code)
	}
}
