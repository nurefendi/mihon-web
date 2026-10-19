package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/crypto/bcrypt"
)

type User struct {
	ID                     int64
	Username, PasswordHash string
}
type Session struct {
	Hash, CSRF, Username string
	UserID               int64
	Expires              time.Time
}
type Preferences struct {
	Theme       string `json:"theme"`
	ReaderMode  string `json:"readerMode"`
	GridColumns int    `json:"gridColumns"`
}
type Store interface {
	User(context.Context, string) (User, error)
	CreateSession(context.Context, Session) error
	Session(context.Context, string) (Session, error)
	DeleteSession(context.Context, string) error
	Preferences(context.Context, int64) (Preferences, error)
	SavePreferences(context.Context, int64, Preferences) error
	Ping(context.Context) error
}
type attempt struct {
	count   int
	expires time.Time
}
type App struct {
	cfg         Config
	store       Store
	assets      fs.FS
	transport   http.RoundTripper
	mu          sync.Mutex
	attempts    map[string]attempt
	uploadSlots chan struct{}
}

func NewApp(c Config, s Store, assets fs.FS, transport http.RoundTripper) (*App, error) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	return &App{cfg: c, store: s, assets: assets, transport: transport, attempts: make(map[string]attempt), uploadSlots: make(chan struct{}, 1)}, nil
}
func token() string {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic("secure random unavailable")
	}
	return hex.EncodeToString(b[:])
}
func digest(s string) string { v := sha256.Sum256([]byte(s)); return hex.EncodeToString(v[:]) }
func (a *App) cookie(w http.ResponseWriter, value string, maxAge int) {
	expires := time.Now().Add(time.Duration(maxAge) * time.Second)
	http.SetCookie(w, &http.Cookie{Name: "mihon_session", Value: value, Path: "/", MaxAge: maxAge, Expires: expires, HttpOnly: true, Secure: strings.HasPrefix(a.cfg.Origin, "https://"), SameSite: http.SameSiteLaxMode})
}

// Only explicitly configured direct peers may assert this single bare IP.
// The trusted proxy must overwrite X-Mihon-Client-IP, never append to it.
// User-supplied X-Forwarded-For and X-Real-IP are never authentication inputs.
func (a *App) loginClient(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	peer := net.ParseIP(host)
	if peer == nil {
		return host
	}
	headers := r.Header.Values("X-Mihon-Client-IP")
	if len(headers) == 1 {
		if client := net.ParseIP(headers[0]); client != nil {
			for _, network := range a.cfg.TrustedProxyCIDRs {
				if network != nil && network.Contains(peer) {
					return client.String()
				}
			}
		}
	}
	return peer.String()
}

func (a *App) allowLogin(remote string) bool {
	host, _, err := net.SplitHostPort(remote)
	if err != nil {
		host = remote
	}
	now := time.Now()
	a.mu.Lock()
	defer a.mu.Unlock()
	for k, v := range a.attempts {
		if !v.expires.After(now) {
			delete(a.attempts, k)
		}
	}
	v := a.attempts[host]
	if v.count == 0 {
		if len(a.attempts) >= 4096 {
			return false
		}
		v.expires = now.Add(15 * time.Minute)
	}
	if v.count >= 10 {
		return false
	}
	v.count++
	a.attempts[host] = v
	return true
}
func (a *App) authenticate(r *http.Request) (Session, bool) {
	c, e := r.Cookie("mihon_session")
	if e != nil || len(c.Value) != 64 {
		return Session{}, false
	}
	s, e := a.store.Session(r.Context(), digest(c.Value))
	return s, e == nil && s.Expires.After(time.Now())
}
func csrfOK(r *http.Request, s Session) bool {
	v := r.Header.Get("X-CSRF-Token")
	if v == "" && r.URL.Path == "/logout" {
		_ = r.ParseForm()
		v = r.PostForm.Get("csrfToken")
	}
	return v != "" && subtle.ConstantTimeCompare([]byte(v), []byte(s.CSRF)) == 1
}
func (a *App) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Cache-Control", "no-store")
	r.Body = http.MaxBytesReader(w, r.Body, 32<<20)
	if r.URL.Path == "/healthz" {
		a.health(w, r)
		return
	}
	if r.URL.Path == "/login" {
		a.login(w, r)
		return
	}
	if !strings.HasPrefix(r.URL.Path, "/api/") && publicAsset(r.URL.Path) {
		a.static(w, r)
		return
	}
	s, ok := a.authenticate(r)
	if !ok {
		if r.URL.Path == "/app-session" || len(r.URL.Path) >= 5 && r.URL.Path[:5] == "/api/" {
			http.Error(w, "authentication required", 401)
		} else {
			http.Redirect(w, r, "/login", 303)
		}
		return
	}
	if r.Method != "GET" && r.Method != "HEAD" && !csrfOK(r, s) {
		http.Error(w, "invalid csrf token", 403)
		return
	}
	if strings.HasPrefix(r.URL.Path, "/api/v1/") {
		if engineNeedsCSRF(r) && !csrfOK(r, s) {
			http.Error(w, "invalid csrf token", 403)
			return
		}
		a.engineProxy(w, r)
		return
	}
	switch r.URL.Path {
	case "/app-session":
		if r.Method != "GET" {
			http.Error(w, "method not allowed", 405)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"username": s.Username, "csrfToken": s.CSRF})
	case "/logout":
		if r.Method != "POST" {
			http.Error(w, "method not allowed", 405)
			return
		}
		if err := a.store.DeleteSession(r.Context(), s.Hash); err != nil {
			http.Error(w, "session unavailable", 503)
			return
		}
		a.cookie(w, "", -1)
		http.Redirect(w, r, "/login", 303)
	case "/api/bridge":
		a.bridge(w, r)
	case "/api/preferences":
		a.preferences(w, r, s)
	default:
		a.static(w, r)
	}
}
func (a *App) login(w http.ResponseWriter, r *http.Request) {
	if r.Method == "GET" {
		b, err := fs.ReadFile(a.assets, "login.html")
		if err != nil {
			http.Error(w, "login unavailable", 503)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(b)
		return
	}
	if r.Method != "POST" {
		http.Error(w, "method not allowed", 405)
		return
	}
	if r.Header.Get("Origin") != a.cfg.Origin {
		http.Error(w, "invalid origin", 403)
		return
	}
	if !a.allowLogin(a.loginClient(r)) {
		http.Error(w, "try later", 429)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8192)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "invalid form", 400)
		return
	}
	u, err := a.store.User(r.Context(), r.PostForm.Get("username"))
	if err != nil || bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(r.PostForm.Get("password"))) != nil {
		http.Error(w, "invalid credentials", 401)
		return
	}
	raw := token()
	s := Session{Hash: digest(raw), CSRF: token(), Username: u.Username, UserID: u.ID, Expires: time.Now().Add(7 * 24 * time.Hour)}
	if err = a.store.CreateSession(r.Context(), s); err != nil {
		http.Error(w, "session unavailable", 503)
		return
	}
	a.cookie(w, raw, 604800)
	http.Redirect(w, r, "/library", 303)
}
