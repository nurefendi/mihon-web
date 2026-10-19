package main

import (
	"fmt"
	"net"
	"net/url"
	"os"
	"strings"

	"golang.org/x/crypto/bcrypt"
)

type Config struct {
	DSN, Origin, Engine, Admin, PasswordHash, Listen string
	TrustedRepositoryURLs                            []string
	TrustedProxyCIDRs                                []*net.IPNet
}

func loadConfig() (Config, error) {
	c := Config{DSN: os.Getenv("MYSQL_DSN"), Origin: os.Getenv("PUBLIC_ORIGIN"), Engine: os.Getenv("ENGINE_URL"), Admin: os.Getenv("BOOTSTRAP_USERNAME"), PasswordHash: os.Getenv("BOOTSTRAP_PASSWORD_HASH"), Listen: os.Getenv("LISTEN_ADDR")}
	if c.Admin == "" {
		c.Admin = "admin"
	}
	if c.Listen == "" {
		c.Listen = ":8080"
	}
	if c.DSN == "" || c.Origin == "" || c.Engine == "" || c.PasswordHash == "" {
		return c, fmt.Errorf("MYSQL_DSN, PUBLIC_ORIGIN, ENGINE_URL and BOOTSTRAP_PASSWORD_HASH are required")
	}
	if _, err := bcrypt.Cost([]byte(c.PasswordHash)); err != nil {
		return c, fmt.Errorf("BOOTSTRAP_PASSWORD_HASH must be bcrypt")
	}
	for _, s := range []string{c.Origin, c.Engine} {
		u, err := url.Parse(s)
		if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.RawQuery != "" || u.Fragment != "" || (u.Path != "" && u.Path != "/") || (s == c.Origin && (u.User != nil || u.Path != "")) {
			return c, fmt.Errorf("invalid origin or engine URL")
		}
	}
	if raw := os.Getenv("TRUSTED_PROXY_CIDRS"); raw != "" {
		for _, entry := range strings.Split(raw, ",") {
			_, network, err := net.ParseCIDR(strings.TrimSpace(entry))
			if err != nil {
				return c, fmt.Errorf("invalid TRUSTED_PROXY_CIDRS entry %q", entry)
			}
			c.TrustedProxyCIDRs = append(c.TrustedProxyCIDRs, network)
		}
	}
	if raw := os.Getenv("TRUSTED_REPOSITORY_URLS"); raw != "" {
		for _, entry := range strings.Split(raw, ",") {
			entry = strings.TrimSpace(entry)
			if !repositoryURLSyntax(entry) {
				return c, fmt.Errorf("TRUSTED_REPOSITORY_URLS must contain exact HTTPS repository URLs")
			}
			c.TrustedRepositoryURLs = append(c.TrustedRepositoryURLs, entry)
		}
	}
	c.Engine = strings.TrimSuffix(c.Engine, "/")
	return c, nil
}
