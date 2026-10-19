package main

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/go-sql-driver/mysql"
)

type SQLStore struct{ db *sql.DB }

func openStore(c Config) (*SQLStore, error) {
	d, err := mysql.ParseDSN(c.DSN)
	if err != nil || d.DBName == "" {
		return nil, fmt.Errorf("MYSQL_DSN must specify a dedicated database")
	}
	d.ParseTime = true
	d.Loc = time.UTC
	d.MultiStatements = false
	d.AllowAllFiles = false
	d.Timeout = 5 * time.Second
	d.ReadTimeout = 10 * time.Second
	d.WriteTimeout = 10 * time.Second
	db, err := sql.Open("mysql", d.FormatDSN())
	if err != nil {
		return nil, fmt.Errorf("database configuration invalid")
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)
	return &SQLStore{db: db}, nil
}
func (s *SQLStore) Initialize(ctx context.Context, admin, hash string) error {
	for _, q := range []string{
		`CREATE TABLE IF NOT EXISTS app_users (id BIGINT NOT NULL PRIMARY KEY, username VARCHAR(191) NOT NULL UNIQUE, password_hash VARCHAR(100) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,
		`CREATE TABLE IF NOT EXISTS app_sessions (token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY, user_id BIGINT NOT NULL, csrf_token CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, expires_at DATETIME(6) NOT NULL, INDEX (expires_at), FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,
		`CREATE TABLE IF NOT EXISTS app_preferences (user_id BIGINT NOT NULL PRIMARY KEY, theme VARCHAR(10) NOT NULL, reader_mode VARCHAR(10) NOT NULL, grid_columns INT NOT NULL, FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`,
	} {
		if _, err := s.db.ExecContext(ctx, q); err != nil {
			return fmt.Errorf("app migration failed: %w", err)
		}
	}
	_, err := s.db.ExecContext(ctx, `INSERT INTO app_users (id,username,password_hash) VALUES (1,?,?) ON DUPLICATE KEY UPDATE id=id`, admin, hash)
	return err
}
func (s *SQLStore) User(ctx context.Context, name string) (User, error) {
	var u User
	err := s.db.QueryRowContext(ctx, `SELECT id,username,password_hash FROM app_users WHERE id=1 AND BINARY username=?`, name).Scan(&u.ID, &u.Username, &u.PasswordHash)
	return u, err
}
func (s *SQLStore) CreateSession(ctx context.Context, v Session) error {
	if _, err := s.db.ExecContext(ctx, `DELETE FROM app_sessions WHERE expires_at<=UTC_TIMESTAMP(6)`); err != nil {
		return err
	}
	_, err := s.db.ExecContext(ctx, `INSERT INTO app_sessions (token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)`, v.Hash, v.UserID, v.CSRF, v.Expires.UTC())
	return err
}
func (s *SQLStore) Session(ctx context.Context, h string) (Session, error) {
	var v Session
	err := s.db.QueryRowContext(ctx, `SELECT s.token_hash,s.user_id,s.csrf_token,s.expires_at,u.username FROM app_sessions s JOIN app_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>UTC_TIMESTAMP(6) AND u.id=1`, h).Scan(&v.Hash, &v.UserID, &v.CSRF, &v.Expires, &v.Username)
	return v, err
}
func (s *SQLStore) DeleteSession(ctx context.Context, h string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM app_sessions WHERE token_hash=?`, h)
	return err
}
func (s *SQLStore) Preferences(ctx context.Context, id int64) (Preferences, error) {
	p := Preferences{Theme: "system", ReaderMode: "webtoon", GridColumns: 4}
	err := s.db.QueryRowContext(ctx, `SELECT theme,reader_mode,grid_columns FROM app_preferences WHERE user_id=?`, id).Scan(&p.Theme, &p.ReaderMode, &p.GridColumns)
	if err == sql.ErrNoRows {
		return p, nil
	}
	return p, err
}
func (s *SQLStore) SavePreferences(ctx context.Context, id int64, p Preferences) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO app_preferences (user_id,theme,reader_mode,grid_columns) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE theme=VALUES(theme), reader_mode=VALUES(reader_mode), grid_columns=VALUES(grid_columns)`, id, p.Theme, p.ReaderMode, p.GridColumns)
	return err
}
func (s *SQLStore) Ping(ctx context.Context) error { return s.db.PingContext(ctx) }
