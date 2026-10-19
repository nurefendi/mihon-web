package main

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"path"
	"strings"
	"time"
)

func allowedEnginePath(u *url.URL) bool {
	p := u.Path
	if !strings.HasPrefix(p, "/api/v1/") || strings.Contains(p, "\\") || strings.Contains(p, "//") || strings.Contains(u.EscapedPath(), "%") || path.Clean(p) != strings.TrimSuffix(p, "/") {
		return false
	}
	ns := strings.Split(strings.TrimPrefix(p, "/api/v1/"), "/")[0]
	switch ns {
	case "source", "extension", "manga", "category", "download", "downloads", "chapter", "update", "backup", "track", "tracker", "history":
		return true
	}
	return false
}
func engineNeedsCSRF(r *http.Request) bool {
	if r.Method != "GET" {
		return true
	}
	parts := strings.Split(strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/v1/"), "/"), "/")
	if len(parts) > 0 {
		switch parts[0] {
		case "manga":
			if len(parts) >= 3 && parts[2] == "library" || len(parts) >= 4 && parts[2] == "category" {
				return true
			}
		case "extension":
			if len(parts) >= 2 && (parts[1] == "install" || parts[1] == "update" || parts[1] == "uninstall") {
				return true
			}
		case "downloads":
			if len(parts) >= 2 && (parts[1] == "start" || parts[1] == "stop" || parts[1] == "clear") {
				return true
			}
		case "download":
			return true
		}
	}
	for _, key := range []string{"updateProgress", "markAsRead", "reset"} {
		for _, v := range r.URL.Query()[key] {
			if !strings.EqualFold(v, "false") {
				return true
			}
		}
	}
	return false
}
func (a *App) engineProxy(w http.ResponseWriter, r *http.Request) {
	if !allowedEnginePath(r.URL) {
		http.Error(w, "engine endpoint forbidden", 403)
		return
	}
	if r.ContentLength > 32<<20 {
		http.Error(w, "upload too large", 413)
		return
	}
	// Buffer bounded uploads before forwarding: oversize chunked bodies must never
	// partially mutate an upstream resource.
	if r.Body != nil && r.Method != "GET" {
		// Hold the single slot until forwarding finishes: buffered bytes remain
		// live while the engine consumes them. Never read a rejected request body.
		select {
		case a.uploadSlots <- struct{}{}:
			defer func() { <-a.uploadSlots }()
		default:
			http.Error(w, "another upload is in progress; try later", http.StatusServiceUnavailable)
			return
		}
		b, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "invalid or oversized upload", 413)
			return
		}
		r.Body = io.NopCloser(bytes.NewReader(b))
		r.ContentLength = int64(len(b))
	}
	target, err := url.Parse(a.cfg.Engine)
	if err != nil {
		http.Error(w, "engine unavailable", 502)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 45*time.Second)
	defer cancel()
	r = r.WithContext(ctx)
	proxy := httputil.ReverseProxy{
		Transport: a.transport,
		Rewrite: func(p *httputil.ProxyRequest) {
			p.SetURL(target)
			p.Out.Host = target.Host
			p.Out.Header.Del("Cookie")
			p.Out.Header.Del("Authorization")
			p.Out.Header.Del("X-CSRF-Token")
			p.Out.Header.Del("Origin")
			p.Out.Header.Del("Referer")
			p.Out.Header.Del("Forwarded")
			for k := range p.Out.Header {
				if strings.HasPrefix(strings.ToLower(k), "x-forwarded-") {
					p.Out.Header.Del(k)
				}
			}
			if target.User != nil {
				password, _ := target.User.Password()
				p.Out.SetBasicAuth(target.User.Username(), password)
			}
		},
		ModifyResponse: func(resp *http.Response) error {
			resp.Header.Del("Set-Cookie")
			resp.Header.Del("WWW-Authenticate")
			resp.Header.Del("Access-Control-Allow-Origin")
			resp.Header.Del("Access-Control-Allow-Credentials")
			resp.Header.Set("Cache-Control", "no-store")
			if resp.StatusCode >= 300 && resp.StatusCode < 400 {
				resp.Header.Del("Location")
				resp.StatusCode = 502
				resp.Status = "502 Bad Gateway"
			}
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) { http.Error(w, "engine unavailable", 502) },
	}
	proxy.ServeHTTP(w, r)
}
