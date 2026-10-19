package main

import (
	"bytes"
	"io/fs"
	"mime"
	"net/http"
	"path"
	"regexp"
	"strings"
	"time"
)

var mangaRoute = regexp.MustCompile(`^/manga/[0-9]+$`)
var readerRoute = regexp.MustCompile(`^/reader/[0-9]+/[0-9]+$`)

func publicAsset(p string) bool {
	if strings.Contains(p, "\\") || strings.Contains(p, "//") || path.Clean(p) != p || strings.HasPrefix(path.Base(p), ".") {
		return false
	}
	switch path.Ext(p) {
	case ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2":
		return true
	}
	return false
}
func (a *App) static(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" && r.Method != "HEAD" {
		http.Error(w, "method not allowed", 405)
		return
	}
	name := strings.TrimPrefix(r.URL.Path, "/")
	switch r.URL.Path {
	case "/", "/library", "/browse", "/updates", "/history", "/more":
		name = "index.html"
	default:
		if mangaRoute.MatchString(r.URL.Path) || readerRoute.MatchString(r.URL.Path) {
			name = "index.html"
		} else if !publicAsset(r.URL.Path) {
			http.NotFound(w, r)
			return
		}
	}
	b, err := fs.ReadFile(a.assets, name)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	typ := mime.TypeByExtension(path.Ext(name))
	if typ != "" {
		w.Header().Set("Content-Type", typ)
	}
	http.ServeContent(w, r, name, time.Time{}, bytes.NewReader(b))
}
