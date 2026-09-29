// Package main implements CLI tools for University Ecosystem administration.
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/spf13/cobra"
)

var (
	redisURL string
	verbose  bool

	newRedisClientFunc = newRedisClient
	confirmActionFunc  = confirmAction
)

func main() {
	if err := newRootCmd().Execute(); err != nil {
		os.Exit(1)
	}
}

func newRootCmd() *cobra.Command {
	rootCmd := &cobra.Command{
		Use:   "uni-cli",
		Short: "University Ecosystem CLI tools",
		Long:  "Administration tools for the University Ecosystem platform",
	}

	// Global flags
	rootCmd.PersistentFlags().StringVar(&redisURL, "redis", getEnv("REDIS_URL", "redis://localhost:6379/0"), "Redis connection URL")
	rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "Verbose output")

	// Add commands
	rootCmd.AddCommand(cacheCmd())
	rootCmd.AddCommand(healthCmd())
	rootCmd.AddCommand(metricsCmd())

	return rootCmd
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// cacheCmd returns the cache management command group.
func cacheCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "cache",
		Short: "Cache management commands",
	}

	// Clear cache
	clearCmd := &cobra.Command{
		Use:   "clear [pattern]",
		Short: "Clear cache keys matching pattern",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			pattern := "*"
			if len(args) > 0 {
				pattern = args[0]
			}

			client, err := newRedisClientFunc()
			if err != nil {
				return fmt.Errorf("failed to connect to Redis: %w", err)
			}
			defer func() { _ = client.Close() }() //nolint:errcheck // best-effort cleanup

			ctx := context.Background()

			// Find keys with cursor-based SCAN.  KEYS blocks Redis' single-threaded
			// event loop for the duration of a full keyspace traversal and can take
			// the entire platform offline on a production-sized cache.
			var keys []string
			var cursor uint64
			for {
				batch, nextCursor, scanErr := client.Scan(ctx, cursor, pattern, 1000).Result()
				if scanErr != nil {
					return scanErr
				}
				keys = append(keys, batch...)
				cursor = nextCursor
				if cursor == 0 {
					break
				}
			}

			if len(keys) == 0 {
				fmt.Println("No keys found matching pattern:", pattern)
				return nil
			}

			// Confirm
			fmt.Printf("Found %d keys matching '%s'\n", len(keys), pattern)
			if !confirmActionFunc("Clear these keys?") {
				fmt.Println("Aborted")
				return nil
			}

			// Delete in bounded batches so a very large cache clear does not create
			// an oversized Redis command or retain one huge argument frame.
			var deleted int64
			for start := 0; start < len(keys); start += 1000 {
				end := start + 1000
				if end > len(keys) {
					end = len(keys)
				}
				deletedBatch, delErr := client.Del(ctx, keys[start:end]...).Result()
				if delErr != nil {
					return delErr
				}
				deleted += deletedBatch
			}

			fmt.Printf("Deleted %d keys\n", deleted)
			return nil
		},
	}

	// Cache stats
	statsCmd := &cobra.Command{
		Use:   "stats",
		Short: "Show cache statistics",
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newRedisClientFunc()
			if err != nil {
				return err
			}
			defer func() { _ = client.Close() }() //nolint:errcheck // best-effort cleanup

			ctx := context.Background()

			info, err := client.Info(ctx, "memory", "keyspace").Result()
			if err != nil {
				return err
			}

			fmt.Println("Cache Statistics:")
			fmt.Println("-----------------")
			fmt.Println(info)
			return nil
		},
	}

	cmd.AddCommand(clearCmd, statsCmd)
	return cmd
}

// healthCmd returns the health check command.
//
// A failing dependency yields a non-zero exit code (returns an error) so that
// monitoring tools and CI gates can rely on the exit status — a health check
// that always exits 0 is useless for automation.
func healthCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "health",
		Short: "Check system health",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("System Health Check")
			fmt.Println("-------------------")

			healthy := true

			// Check Redis
			fmt.Print("Redis: ")
			client, err := newRedisClientFunc()
			if err != nil {
				fmt.Println("❌ ", err)
				healthy = false
			} else {
				ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()
				if err := client.Ping(ctx).Err(); err != nil {
					fmt.Println("❌ ", err)
					healthy = false
				} else {
					fmt.Println("✅ Connected")
				}
				_ = client.Close() //nolint:errcheck // best-effort cleanup
			}

			// Add more health checks as needed.
			fmt.Println("\nAll checks completed")
			if !healthy {
				return fmt.Errorf("one or more health checks failed")
			}
			return nil
		},
	}
}

// metricsCmd returns metrics commands.
func metricsCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "metrics",
		Short: "View system metrics",
	}

	showCmd := &cobra.Command{
		Use:   "show",
		Short: "Show current metrics",
		RunE: func(cmd *cobra.Command, args []string) error {
			client, err := newRedisClientFunc()
			if err != nil {
				return err
			}
			defer func() { _ = client.Close() }() //nolint:errcheck // best-effort cleanup

			ctx := context.Background()

			// Get basic metrics from Redis
			dbSize, err := client.DBSize(ctx).Result()
			if err != nil {
				return err
			}
			info, err := client.Info(ctx, "stats").Result()
			if err != nil {
				return err
			}

			fmt.Println("System Metrics")
			fmt.Println("--------------")
			fmt.Printf("Cache keys: %d\n", dbSize)
			if verbose {
				fmt.Println("\nDetailed stats:")
				fmt.Println(info)
			}

			return nil
		},
	}

	cmd.AddCommand(showCmd)
	return cmd
}

func newRedisClient() (*redis.Client, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return redis.NewClient(opt), nil
}

func confirmAction(prompt string) bool {
	var response string
	fmt.Printf("%s [y/N]: ", prompt)
	fmt.Scanln(&response) //nolint:errcheck // interactive prompt; empty/err input treated as "no"
	return response == "y" || response == "Y"
}
