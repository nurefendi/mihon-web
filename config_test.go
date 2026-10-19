package main

import (
	"golang.org/x/crypto/bcrypt"
	"testing"
)

func validConfigEnvironment(t *testing.T) {
	t.Helper()
	hash, _ := bcrypt.GenerateFromPassword([]byte("test-only"), bcrypt.MinCost)
	t.Setenv("MYSQL_DSN", "test")
	t.Setenv("PUBLIC_ORIGIN", "https://mg.example")
	t.Setenv("ENGINE_URL", "http://engine:4567")
	t.Setenv("BOOTSTRAP_PASSWORD_HASH", string(hash))
	t.Setenv("TRUSTED_REPOSITORY_URLS", "")
	t.Setenv("TRUSTED_PROXY_CIDRS", "")
}

func TestTrustedProxyConfigRejectsInvalidCIDRs(t *testing.T) {
	validConfigEnvironment(t)
	for _, raw := range []string{"172.18.0.5", "not-a-cidr", "172.18.0.5/33", "172.18.0.5/32,,::1/128"} {
		t.Setenv("TRUSTED_PROXY_CIDRS", raw)
		if _, err := loadConfig(); err == nil {
			t.Fatalf("accepted invalid TRUSTED_PROXY_CIDRS %q", raw)
		}
	}
}

func TestTrustedRepositoryConfig(t *testing.T) {
	validConfigEnvironment(t)
	c, err := loadConfig()
	if err != nil || len(c.TrustedRepositoryURLs) != 0 || len(c.TrustedProxyCIDRs) != 0 {
		t.Fatalf("defaults: %+v %v", c, err)
	}
	t.Setenv("TRUSTED_REPOSITORY_URLS", "https://repo.example/Index.json, https://other.example/index.json")
	c, err = loadConfig()
	if err != nil || len(c.TrustedRepositoryURLs) != 2 || c.TrustedRepositoryURLs[0] != "https://repo.example/Index.json" {
		t.Fatalf("configured: %+v %v", c, err)
	}
	for _, raw := range []string{"http://repo.example/index.json", "https://user:pass@repo.example/index.json", "https:///index.json", "https://repo.example/one,,https://repo.example/two"} {
		t.Setenv("TRUSTED_REPOSITORY_URLS", raw)
		if _, err := loadConfig(); err == nil {
			t.Fatalf("accepted %q", raw)
		}
	}
}

func TestConfigFailsClosed(t *testing.T) {
	for _, key := range []string{"MYSQL_DSN", "PUBLIC_ORIGIN", "ENGINE_URL", "BOOTSTRAP_PASSWORD_HASH", "BOOTSTRAP_USERNAME"} {
		t.Setenv(key, "")
	}
	if _, err := loadConfig(); err == nil {
		t.Fatal("missing configuration accepted")
	}
	hash, _ := bcrypt.GenerateFromPassword([]byte("example-only"), bcrypt.MinCost)
	t.Setenv("MYSQL_DSN", "u:p@tcp(db:3306)/mihon")
	t.Setenv("PUBLIC_ORIGIN", "https://mg.namiza.id")
	t.Setenv("ENGINE_URL", "http://engine:4567")
	t.Setenv("BOOTSTRAP_PASSWORD_HASH", string(hash))
	c, err := loadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if c.Admin != "admin" {
		t.Fatal(c.Admin)
	}
	for _, origin := range []string{"https://mg.namiza.id/path", "ftp://host", "https://u:p@host", "https://host?q=x"} {
		t.Setenv("PUBLIC_ORIGIN", origin)
		if _, err := loadConfig(); err == nil {
			t.Fatalf("accepted %s", origin)
		}
	}
}
