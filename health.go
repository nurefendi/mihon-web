package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"time"
)

func (a *App) health(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "method not allowed", 405)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	dbOK := a.store.Ping(ctx) == nil
	u, err := url.Parse(a.cfg.Engine)
	engineOK := false
	if err == nil {
		u.Path = "/api/v1/settings/about"
		req, e := http.NewRequestWithContext(ctx, "GET", u.String(), nil)
		if e == nil {
			if u.User != nil {
				p, _ := u.User.Password()
				req.SetBasicAuth(u.User.Username(), p)
				req.URL.User = nil
			}
			resp, e := a.transport.RoundTrip(req)
			if e == nil {
				engineOK = resp.StatusCode == 200
				_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
				_ = resp.Body.Close()
			}
		}
	}
	w.Header().Set("Content-Type", "application/json")
	if !dbOK || !engineOK {
		w.WriteHeader(503)
	}
	_ = json.NewEncoder(w).Encode(map[string]bool{"ok": dbOK && engineOK, "database": dbOK, "engine": engineOK})
}
