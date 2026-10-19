package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var bridgeQueries = map[string]string{
	"library":          `query($first:Int!,$offset:Int!){mangas(condition:{inLibrary:true},first:$first,offset:$offset){nodes{id title thumbnailUrl inLibrary sourceId} totalCount pageInfo{hasNextPage endCursor}}}`,
	"history":          `query($first:Int!,$offset:Int!){chapters(filter:{lastReadAt:{greaterThan:"0"}},order:[{by:LAST_READ_AT,byType:DESC}],first:$first,offset:$offset){nodes{id name mangaId lastReadAt lastPageRead isRead manga{id title thumbnailUrl}} pageInfo{hasNextPage endCursor} totalCount}}`,
	"downloads":        `query{downloadStatus{state queue{position state progress tries chapter{id name} manga{id title}}}}`,
	"repositories":     `query{extensionStores(first:100){nodes{indexUrl name badgeLabel signingKey contactWebsite contactDiscord isLegacy extensionListUrl}}}`,
	"addRepository":    `mutation($indexUrl:String!){addExtensionStore(input:{indexUrl:$indexUrl}){extensionStore{indexUrl name}}}`,
	"removeRepository": `mutation($indexUrl:String!){removeExtensionStore(input:{indexUrl:$indexUrl}){extensionStore{indexUrl}}}`,
}

// repositoryURLSyntax deliberately performs no DNS or reachability checks.
func repositoryURLSyntax(raw string) bool {
	u, err := url.Parse(raw)
	return err == nil && len(raw) <= 2048 && u.Scheme == "https" && u.Hostname() != "" && u.User == nil && u.Fragment == "" && u.RawQuery == "" && !u.ForceQuery && u.Path != "" && !strings.ContainsAny(raw, "\r\n	 ")
}

func publicRepositoryURL(ctx context.Context, raw string) bool {
	u, err := url.Parse(raw)
	if err != nil || !repositoryURLSyntax(raw) || (u.Port() != "" && u.Port() != "443") {
		return false
	}
	h := strings.ToLower(u.Hostname())
	if net.ParseIP(h) != nil || !strings.Contains(h, ".") || strings.HasSuffix(h, ".") || strings.HasSuffix(h, ".localhost") || strings.HasSuffix(h, ".local") || strings.HasSuffix(h, ".internal") {
		return false
	}
	addrs, err := net.DefaultResolver.LookupIPAddr(ctx, h)
	if err != nil || len(addrs) == 0 {
		return false
	}
	for _, a := range addrs {
		ip := a.IP
		if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() {
			return false
		}
		for _, cidr := range []string{"100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4", "2001:db8::/32"} {
			_, n, _ := net.ParseCIDR(cidr)
			if n.Contains(ip) {
				return false
			}
		}
	}
	return true
}
func bridgeVariables(ctx context.Context, op string, vars map[string]json.RawMessage) (map[string]any, error) {
	result := map[string]any{}
	for k, v := range vars {
		switch {
		case (op == "library" || op == "history") && (k == "first" || k == "offset"):
			var n int
			if json.Unmarshal(v, &n) != nil || n < 0 || (k == "first" && (n < 1 || n > 100)) || n > 1000000 {
				return nil, fmt.Errorf("invalid pagination")
			}
			result[k] = n
		case (op == "addRepository" || op == "removeRepository") && k == "indexUrl":
			var s string
			if json.Unmarshal(v, &s) != nil || !repositoryURLSyntax(s) {
				return nil, fmt.Errorf("repository URL must be HTTPS without credentials")
			}
			if op == "addRepository" && !publicRepositoryURL(ctx, s) {
				return nil, fmt.Errorf("repository URL must be public HTTPS without credentials")
			}
			result[k] = s
		default:
			return nil, fmt.Errorf("unsupported variable")
		}
	}
	if op == "library" || op == "history" {
		if _, ok := result["first"]; !ok {
			result["first"] = 100
			if op == "history" {
				result["first"] = 50
			}
		}
		if _, ok := result["offset"]; !ok {
			result["offset"] = 0
		}
	}
	if op == "addRepository" || op == "removeRepository" {
		if _, ok := result["indexUrl"]; !ok {
			return nil, fmt.Errorf("indexUrl required")
		}
	}
	return result, nil
}
func (a *App) bridge(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "method not allowed", 405)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 8192)
	var input struct {
		Operation string                     `json:"operation"`
		Variables map[string]json.RawMessage `json:"variables"`
	}
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if d.Decode(&input) != nil {
		http.Error(w, "invalid bridge request", 400)
		return
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		http.Error(w, "invalid bridge request", 400)
		return
	}
	query, ok := bridgeQueries[input.Operation]
	if !ok {
		http.Error(w, "unsupported operation", 400)
		return
	}
	// Exact raw comparison must precede DNS and every engine request. These
	// configured metadata/APK publishers are intentionally trusted executable
	// authorities: this does not sandbox recursive URLs and is not a complete
	// egress SSRF firewall.
	if input.Operation == "addRepository" {
		var raw string
		_ = json.Unmarshal(input.Variables["indexUrl"], &raw)
		trusted := false
		for _, allowed := range a.cfg.TrustedRepositoryURLs {
			if raw == allowed {
				trusted = true
				break
			}
		}
		if !trusted {
			http.Error(w, "URL repositori belum diizinkan di server (TRUSTED_REPOSITORY_URLS).", http.StatusForbidden)
			return
		}
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	vars, err := bridgeVariables(ctx, input.Operation, input.Variables)
	if err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	body, _ := json.Marshal(map[string]any{"query": query, "variables": vars})
	u, err := url.Parse(a.cfg.Engine)
	if err != nil {
		http.Error(w, "engine unavailable", 502)
		return
	}
	u.Path = "/api/graphql"
	req, err := http.NewRequestWithContext(ctx, "POST", u.String(), bytes.NewReader(body))
	if err != nil {
		http.Error(w, "engine unavailable", 502)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if u.User != nil {
		p, _ := u.User.Password()
		req.SetBasicAuth(u.User.Username(), p)
		req.URL.User = nil
	}
	resp, err := a.transport.RoundTrip(req)
	if err != nil {
		http.Error(w, "engine unavailable", 502)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		http.Error(w, "engine operation unavailable", 502)
		return
	}
	b, err := io.ReadAll(io.LimitReader(resp.Body, (4<<20)+1))
	if err != nil || len(b) > 4<<20 || !json.Valid(b) {
		http.Error(w, "invalid engine response", 502)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(b)
}
