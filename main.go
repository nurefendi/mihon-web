package main

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

//go:embed web/*
var embeddedWeb embed.FS

func newHTTPServer(addr string, h http.Handler) *http.Server {
	return &http.Server{Addr: addr, Handler: h, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 60 * time.Second, WriteTimeout: 60 * time.Second, IdleTimeout: 90 * time.Second, MaxHeaderBytes: 1 << 20}
}
func run() error {
	c, err := loadConfig()
	if err != nil {
		return err
	}
	s, err := openStore(c)
	if err != nil {
		return err
	}
	defer s.db.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err = s.Ping(ctx); err != nil {
		return fmt.Errorf("database unavailable")
	}
	if err = s.Initialize(ctx, c.Admin, c.PasswordHash); err != nil {
		return fmt.Errorf("app database initialization failed")
	}
	assets, err := fs.Sub(embeddedWeb, "web")
	if err != nil {
		return fmt.Errorf("embedded assets unavailable")
	}
	for _, name := range []string{"index.html", "login.html"} {
		if _, err = fs.Stat(assets, name); err != nil {
			return fmt.Errorf("required embedded asset missing: %s", name)
		}
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ResponseHeaderTimeout = 30 * time.Second
	transport.TLSHandshakeTimeout = 10 * time.Second
	transport.Proxy = nil
	defer transport.CloseIdleConnections()
	app, err := NewApp(c, s, assets, transport)
	if err != nil {
		return err
	}
	server := newHTTPServer(c.Listen, app)
	sigCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-sigCtx.Done():
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			_ = server.Shutdown(ctx)
		case <-done:
		}
	}()
	log.Printf("listening on %s", c.Listen)
	err = server.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return fmt.Errorf("http listener failed")
}
func main() {
	if err := run(); err != nil {
		log.Print(err)
		os.Exit(1)
	}
}
