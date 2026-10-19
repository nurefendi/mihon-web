package main

import (
	"net/http"
	"testing"
	"time"
)

func TestHTTPServerHasTimeouts(t *testing.T) {
	s := newHTTPServer(":8080", http.NotFoundHandler())
	if s.Addr != ":8080" || s.ReadHeaderTimeout <= 0 || s.ReadTimeout <= 0 || s.WriteTimeout < 45*time.Second || s.IdleTimeout <= 0 || s.MaxHeaderBytes > 1<<20 {
		t.Fatalf("unsafe server config: %+v", s)
	}
}
func TestRunFailsClosed(t *testing.T) {
	for _, key := range []string{"MYSQL_DSN", "PUBLIC_ORIGIN", "ENGINE_URL", "BOOTSTRAP_PASSWORD_HASH"} {
		t.Setenv(key, "")
	}
	if err := run(); err == nil {
		t.Fatal("started without credentials")
	}
}
