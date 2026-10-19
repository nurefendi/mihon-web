package main

import (
	"context"
	"os"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"
)

func TestMySQLIntegration(t *testing.T) {
	dsn := os.Getenv("MYSQL_TEST_DSN")
	if dsn == "" {
		t.Skip("MYSQL_TEST_DSN not provided; use an isolated test schema")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	hash, _ := bcrypt.GenerateFromPassword([]byte("integration-only"), bcrypt.MinCost)
	s, err := openStore(Config{DSN: dsn, Admin: "admin", PasswordHash: string(hash)})
	if err != nil {
		t.Fatal(err)
	}
	defer s.db.Close()
	if err = s.Initialize(ctx, "admin", string(hash)); err != nil {
		t.Fatal(err)
	}
	if err = s.Initialize(ctx, "other-admin", string(hash)); err != nil {
		t.Fatal("idempotent migration", err)
	}
	rows, err := s.db.QueryContext(ctx, "SHOW TABLES")
	if err != nil {
		t.Fatal(err)
	}
	tables := map[string]bool{}
	for rows.Next() {
		var n string
		if err = rows.Scan(&n); err != nil {
			t.Fatal(err)
		}
		tables[n] = true
	}
	rows.Close()
	if len(tables) != 3 || !tables["app_users"] || !tables["app_sessions"] || !tables["app_preferences"] {
		t.Fatalf("unexpected schema: %v", tables)
	}
	u, err := s.User(ctx, "admin")
	if err != nil || bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte("integration-only")) != nil {
		t.Fatal("bootstrap failed", err)
	}
	if _, err = s.User(ctx, "other-admin"); err == nil {
		t.Fatal("bootstrap created another admin")
	}
	p, err := s.Preferences(ctx, u.ID)
	if err != nil || !validPreferences(p) {
		t.Fatal("default preferences", p, err)
	}
	p = Preferences{Theme: "dark", ReaderMode: "rtl", GridColumns: 8}
	if err = s.SavePreferences(ctx, u.ID, p); err != nil {
		t.Fatal(err)
	}
	got, err := s.Preferences(ctx, u.ID)
	if err != nil || got != p {
		t.Fatal("preference persistence", got, err)
	}
	raw := token()
	session := Session{Hash: digest(raw), CSRF: token(), UserID: u.ID, Expires: time.Now().Add(time.Hour)}
	if err = s.CreateSession(ctx, session); err != nil {
		t.Fatal(err)
	}
	gotSession, err := s.Session(ctx, session.Hash)
	if err != nil || gotSession.Username != "admin" || gotSession.CSRF != session.CSRF {
		t.Fatal("session persistence", gotSession, err)
	}
	if _, err = s.Session(ctx, raw); err == nil {
		t.Fatal("raw session found")
	}
	if err = s.DeleteSession(ctx, session.Hash); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Session(ctx, session.Hash); err == nil {
		t.Fatal("deleted session accepted")
	}
	session.Hash = digest(token())
	session.Expires = time.Now().Add(-time.Hour)
	if err = s.CreateSession(ctx, session); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Session(ctx, session.Hash); err == nil {
		t.Fatal("expired session accepted")
	}
	if err = s.Ping(ctx); err != nil {
		t.Fatal(err)
	}
}
