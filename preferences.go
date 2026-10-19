package main

import (
	"encoding/json"
	"io"
	"net/http"
)

func validPreferences(p Preferences) bool {
	return (p.Theme == "dark" || p.Theme == "light" || p.Theme == "system") && (p.ReaderMode == "webtoon" || p.ReaderMode == "ltr" || p.ReaderMode == "rtl") && p.GridColumns >= 2 && p.GridColumns <= 8
}
func (a *App) preferences(w http.ResponseWriter, r *http.Request, s Session) {
	var p Preferences
	var err error
	switch r.Method {
	case "GET":
		p, err = a.store.Preferences(r.Context(), s.UserID)
	case "PUT":
		r.Body = http.MaxBytesReader(w, r.Body, 4096)
		d := json.NewDecoder(r.Body)
		d.DisallowUnknownFields()
		if d.Decode(&p) != nil || !validPreferences(p) {
			http.Error(w, "invalid preferences", 400)
			return
		}
		var extra any
		if d.Decode(&extra) != io.EOF {
			http.Error(w, "invalid preferences", 400)
			return
		}
		err = a.store.SavePreferences(r.Context(), s.UserID, p)
	default:
		http.Error(w, "method not allowed", 405)
		return
	}
	if err != nil {
		http.Error(w, "preferences unavailable", 503)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(p)
}
