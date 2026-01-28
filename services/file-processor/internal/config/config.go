package config

import (
	"fmt"

	"github.com/spf13/viper"
)

// Config holds processor configuration
type Config struct {
	GRPCPort       string `mapstructure:"grpc_port"`
	NatsURL        string `mapstructure:"nats_url"`
	TemporalHost   string `mapstructure:"temporal_host"`
	MinioBucket    string `mapstructure:"minio_bucket"`
	MinioEndpoint  string `mapstructure:"minio_endpoint"`
	MinioAccessKey string `mapstructure:"minio_access_key"`
	MinioSecretKey string `mapstructure:"minio_secret_key"`
	MinioSecure    bool   `mapstructure:"minio_secure"`
	GraphQLPort    string `mapstructure:"graphql_port"`
	JWTSecret      string `mapstructure:"jwt_secret"`
	SentryDSN      string `mapstructure:"sentry_dsn"`
	Environment    string `mapstructure:"environment"`
}

// Load loads the configuration from environment variables using Viper
func Load() (*Config, error) {
	viper.SetEnvPrefix("") // No prefix, or use "FP" if strictnamespacing needed, but existing envs are loose
	viper.AutomaticEnv()

	// Default values
	viper.SetDefault("grpc_port", "50051")
	viper.SetDefault("graphql_port", "8080")
	viper.SetDefault("nats_url", "nats://nats:4222")
	viper.SetDefault("temporal_host", "temporal:7233")
	viper.SetDefault("minio_bucket", "uploads")
	viper.SetDefault("minio_endpoint", "minio:9000")
	viper.SetDefault("minio_access_key", "minioadmin")
	viper.SetDefault("minio_secret_key", "minioadmin")
	viper.SetDefault("minio_secure", false)

	_ = viper.BindEnv("grpc_port", "GRPC_PORT")
	_ = viper.BindEnv("nats_url", "NATS_URL")
	_ = viper.BindEnv("temporal_host", "TEMPORAL_HOST")
	_ = viper.BindEnv("minio_bucket", "MINIO_BUCKET")
	_ = viper.BindEnv("minio_endpoint", "MINIO_ENDPOINT")
	_ = viper.BindEnv("minio_access_key", "MINIO_ACCESS_KEY")
	_ = viper.BindEnv("minio_secret_key", "MINIO_SECRET_KEY")
	_ = viper.BindEnv("minio_secure", "MINIO_SECURE")
	_ = viper.BindEnv("jwt_secret", "JWT_SECRET")
	_ = viper.BindEnv("sentry_dsn", "SENTRY_DSN")
	_ = viper.BindEnv("environment", "VITE_ENVIRONMENT")

	var cfg Config
	if err := viper.Unmarshal(&cfg); err != nil {
		return nil, err
	}

	if cfg.MinioAccessKey == "" || cfg.MinioSecretKey == "" {
		return nil, fmt.Errorf("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")
	}

	return &cfg, nil
}
