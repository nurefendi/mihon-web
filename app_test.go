package main

import (
	"context"
	"encoding/json"
	"errors"
	"golang.org/x/crypto/bcrypt"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"testing/fstest"
	"time"
)

type memoryStore struct {
	user     User
	sessions map[string]Session
	prefs    Preferences
	down     bool
}

func (m *memoryStore) User(ctx context.Context, name string) (User, error) {
	if name != m.user.Username {
		return User{}, errors.New("missing")
	}
	return m.user, nil
}
func (m *memoryStore) CreateSession(ctx context.Context, s Session) error {
	m.sessions[s.Hash] = s
	return nil
}
func (m *memoryStore) Session(ctx context.Context, h string) (Session, error) {
	s, ok := m.sessions[h]
	if !ok || !s.Expires.After(time.Now()) {
		return s, errors.New("missing")
	}
	return s, nil
}
func (m *memoryStore) DeleteSession(ctx context.Context, h string) error {
	delete(m.sessions, h)
	return nil
}
func (m *memoryStore) Preferences(ctx context.Context, id int64) (Preferences, error) {
	return m.prefs, nil
}
func (m *memoryStore) SavePreferences(ctx context.Context, id int64, p Preferences) error {
	m.prefs = p
	return nil
}
func (m *memoryStore) Ping(ctx context.Context) error {
	if m.down {
		return errors.New("secret db error")
	}
	return nil
}
func testApp(t *testing.T) (*App, *memoryStore) {
	t.Helper()
	h, _ := bcrypt.GenerateFromPassword([]byte("test-password"), bcrypt.MinCost)
	s := &memoryStore{user: User{ID: 1, Username: "admin", PasswordHash: string(h)}, sessions: map[string]Session{}, prefs: Preferences{Theme: "system", ReaderMode: "webtoon", GridColumns: 4}}
	assets := fstest.MapFS{"index.html": {Data: []byte("INDEX")}, "login.html": {Data: []byte("LOGIN")}, "app.js": {Data: []byte("console.log('ok')")}}
	var files fs.FS = assets
	a, err := NewApp(Config{Origin: "https://mg.example", Engine: "http://engine"}, s, files, http.DefaultTransport)
	if err != nil {
		t.Fatal(err)
	}
	return a, s
}
func request(a http.Handler, method, path, body string, cookie *http.Cookie, origin, csrf string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	if cookie != nil {
		r.AddCookie(cookie)
	}
	if origin != "" {
		r.Header.Set("Origin", origin)
	}
	if csrf != "" {
		r.Header.Set("X-CSRF-Token", csrf)
	}
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	return w
}
func login(t *testing.T, a *App) (*http.Cookie, string) {
	t.Helper()
	w := request(a, "POST", "/login", url.Values{"username": {"admin"}, "password": {"test-password"}}.Encode(), nil, "https://mg.example", "")
	if w.Code != 303 {
		t.Fatalf("login %d %s", w.Code, w.Body.String())
	}
	cs := w.Result().Cookies()
	if len(cs) == 0 {
		t.Fatal("no cookie")
	}
	w = request(a, "GET", "/app-session", "", cs[0], "", "")
	var s struct {
		Username string `json:"username"`
		CSRF     string `json:"csrfToken"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &s); err != nil || s.CSRF == "" || s.Username != "admin" {
		t.Fatalf("session: %s", w.Body.String())
	}
	return cs[0], s.CSRF
}
func TestStaticRoutes(t *testing.T) {
	a, _ := testApp(t)
	c, _ := login(t, a)
	for _, p := range []string{"/", "/library", "/browse", "/updates", "/history", "/more", "/manga/42", "/reader/42/0"} {
		w := request(a, "GET", p, "", c, "", "")
		if w.Code != 200 || w.Body.String() != "INDEX" {
			t.Fatalf("SPA %s: %d %s", p, w.Code, w.Body.String())
		}
	}
	for _, p := range []string{"/nonsense", "/manga/no", "/library/random", "/.keep", "/index.html", "/reader/no"} {
		if w := request(a, "GET", p, "", c, "", ""); w.Code != 404 {
			t.Fatalf("unknown %s: %d", p, w.Code)
		}
	}
	w := request(a, "GET", "/app.js", "", nil, "", "")
	if w.Code != 200 || !strings.Contains(w.Header().Get("Content-Type"), "javascript") {
		t.Fatalf("js: %d %v", w.Code, w.Header())
	}
	if w = request(a, "GET", "/login", "", nil, "", ""); w.Code != 200 || w.Body.String() != "LOGIN" {
		t.Fatal("login missing")
	}
	for _, k := range []string{"Content-Security-Policy", "Referrer-Policy", "X-Content-Type-Options"} {
		if w.Header().Get(k) == "" {
			t.Fatal("missing " + k)
		}
	}
}
func TestHealthChecksDependencies(t *testing.T) {
	a, s := testApp(t)
	engineStatus := 200
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/settings/about" {
			t.Errorf("readiness path %s", r.URL.Path)
		}
		w.WriteHeader(engineStatus)
	}))
	defer up.Close()
	a.cfg.Engine = up.URL
	if w := request(a, "GET", "/healthz", "", nil, "", ""); w.Code != 200 {
		t.Fatalf("health %d %s", w.Code, w.Body.String())
	}
	s.down = true
	if w := request(a, "GET", "/healthz", "", nil, "", ""); w.Code != 503 || strings.Contains(w.Body.String(), "secret") {
		t.Fatal("db failure not protected")
	}
	s.down = false
	engineStatus = 503
	if w := request(a, "GET", "/healthz", "", nil, "", ""); w.Code != 503 {
		t.Fatal("engine failure ignored")
	}
}
func TestEngineProxySecurity(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/manga/42" || r.URL.RawQuery != "online=true" || r.Method != "PATCH" {
			t.Errorf("upstream request %s %s", r.Method, r.URL)
		}
		for _, key := range []string{"Cookie", "X-CSRF-Token", "X-Forwarded-For", "Forwarded"} {
			if r.Header.Get(key) != "" {
				t.Errorf("leaked %s", key)
			}
		}
		if r.Header.Get("Authorization") != "Basic ZW5naW5lOnNlY3JldA==" {
			t.Error("wrong engine credentials")
		}
		w.Header().Set("Set-Cookie", "engine=secret")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(201)
		_, _ = w.Write([]byte(`{"id":42}`))
	}))
	defer upstream.Close()
	a, _ := testApp(t)
	a.cfg.Engine = strings.Replace(upstream.URL, "http://", "http://engine:secret@", 1)
	c, csrf := login(t, a)
	for _, p := range []string{"/api/v1/settings", "/api/v1/server/about", "/api/v1/unknown", "/api/v1/manga/../settings", "/api/v1/manga/%2e%2e/settings", "/api/v1/manga//../settings"} {
		if w := request(a, "GET", p, "", c, "", ""); w.Code != 403 {
			t.Fatalf("forbidden %s returned %d", p, w.Code)
		}
	}
	if w := request(a, "PATCH", "/api/v1/manga/42", "", c, "", ""); w.Code != 403 {
		t.Fatal("missing csrf accepted")
	}
	r := httptest.NewRequest("PATCH", "/api/v1/manga/42?online=true", strings.NewReader(`{}`))
	r.AddCookie(c)
	r.Header.Set("X-CSRF-Token", csrf)
	r.Header.Set("Authorization", "Bearer browser-secret")
	r.Header.Set("X-Forwarded-For", "spoof")
	r.Header.Set("Forwarded", "for=spoof")
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	if w.Code != 201 || w.Body.String() != `{"id":42}` || w.Header().Get("Set-Cookie") != "" {
		t.Fatalf("proxy %d %s %v", w.Code, w.Body.String(), w.Header())
	}
}
func TestPreferencesValidation(t *testing.T) {
	a, s := testApp(t)
	c, csrf := login(t, a)
	w := request(a, "GET", "/api/preferences", "", c, "", "")
	if w.Code != 200 {
		t.Fatalf("preferences GET %d", w.Code)
	}
	for _, body := range []string{`{"theme":"dark","readerMode":"rtl","gridColumns":8}`, `{"theme":"system","readerMode":"webtoon","gridColumns":2}`} {
		w = request(a, "PUT", "/api/preferences", body, c, "", csrf)
		if w.Code != 200 {
			t.Fatalf("PUT %d %s", w.Code, w.Body.String())
		}
	}
	if s.prefs.GridColumns != 2 {
		t.Fatal(s.prefs)
	}
	for _, body := range []string{`{"theme":"evil","readerMode":"rtl","gridColumns":4}`, `{"theme":"dark","readerMode":"foo","gridColumns":4}`, `{"theme":"dark","readerMode":"ltr","gridColumns":9}`, `{"theme":"dark","readerMode":"ltr","gridColumns":3.5}`, `{"theme":"dark","readerMode":"ltr","gridColumns":4,"admin":true}`, `{} {}`} {
		w = request(a, "PUT", "/api/preferences", body, c, "", csrf)
		if w.Code != 400 {
			t.Fatalf("accepted %s: %d", body, w.Code)
		}
	}
	if w = request(a, "PUT", "/api/preferences", `{}`, c, "", ""); w.Code != 403 {
		t.Fatal("no CSRF accepted")
	}
}
func TestAuthenticationLifecycle(t *testing.T) {
	a, s := testApp(t)
	w := request(a, "GET", "/library", "", nil, "", "")
	if w.Code != 303 || w.Header().Get("Location") != "/login" {
		t.Fatalf("anonymous: %d", w.Code)
	}
	if w = request(a, "POST", "/login", "username=admin&password=test-password", nil, "", ""); w.Code != 403 {
		t.Fatal("login missing Origin accepted")
	}
	if w = request(a, "POST", "/login", "username=admin&password=wrong", nil, "https://mg.example", ""); w.Code != 401 {
		t.Fatal("bad password accepted")
	}
	c, csrf := login(t, a)
	if !c.Secure || !c.HttpOnly || c.SameSite != http.SameSiteLaxMode || c.MaxAge != 604800 || c.Expires.Before(time.Now().Add(6*24*time.Hour)) {
		t.Fatalf("unsafe cookie %+v", c)
	}
	if _, ok := s.sessions[c.Value]; ok {
		t.Fatal("raw session persisted")
	}
	if w = request(a, "POST", "/logout", "", c, "", ""); w.Code != 403 {
		t.Fatal("logout without csrf accepted")
	}
	if w = request(a, "POST", "/logout", "", c, "", csrf); w.Code != 303 {
		t.Fatal(w.Code)
	}
	if w = request(a, "GET", "/app-session", "", c, "", ""); w.Code != 401 {
		t.Fatal("revoked session accepted")
	}
}
