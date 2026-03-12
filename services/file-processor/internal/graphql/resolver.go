package graphql

import (
	"context"
	"fmt"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
)

type Resolver struct {
	TemporalClient client.Client
	MinioBucket    string
}

func (r *Resolver) Health() string {
	return "OK"
}

func sanitizeKey(key string) (string, error) {
	cleaned := path.Clean("/" + key)
	if cleaned == "/" || strings.Contains(key, "..") {
		return "", fmt.Errorf("invalid path string")
	}
	return cleaned[1:], nil
}

func (r *Resolver) File(args struct{ ID string }) *FileResolver {
	safeID, err := sanitizeKey(args.ID)
	if err != nil {
		// In a real GraphQL context, return an error, but here we fallback to safe empty
		safeID = "invalid-path"
	}

	escapedSafeID := url.PathEscape(safeID)

	return &FileResolver{
		id:  safeID,
		url: fmt.Sprintf("http://localhost:9000/%s/%s", r.MinioBucket, escapedSafeID),
	}
}

func (r *Resolver) ProcessFile(ctx context.Context, args struct{ Input ProcessFileInput }) (*FileJobResolver, error) {
	options := make(map[string]interface{})
	if args.Input.Width != nil {
		options["width"] = int(*args.Input.Width)
	}
	if args.Input.Height != nil {
		options["height"] = int(*args.Input.Height)
	}

	safeSourceKey, err := sanitizeKey(args.Input.SourceKey)
	if err != nil {
		return nil, fmt.Errorf("invalid source key: %v", err)
	}

	safeDestKey, err := sanitizeKey(args.Input.DestKey)
	if err != nil {
		return nil, fmt.Errorf("invalid destination key: %v", err)
	}

	job := workflow.ProcessJob{
		ID:        generateID(),
		Type:      args.Input.Type,
		SourceKey: safeSourceKey,
		DestKey:   safeDestKey,
		Options:   options,
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:        "graphql-" + job.ID,
		TaskQueue: "FILE_PROCESSING_TASK_QUEUE",
	}

	run, err := r.TemporalClient.ExecuteWorkflow(ctx, workflowOptions, workflow.FileProcessingWorkflow, job)
	if err != nil {
		return nil, err
	}

	return &FileJobResolver{
		jobID:     run.GetID(),
		status:    "STARTED",
		resultUrl: "",
	}, nil
}

// -- Sub-Resolvers --

type FileResolver struct {
	id  string
	url string
}

func (r *FileResolver) ID() string    { return r.id }
func (r *FileResolver) URL() string   { return r.url }
func (r *FileResolver) Size() *int32  { s := int32(0); return &s } // Mock
func (r *FileResolver) Type() *string { t := "unknown"; return &t }

type FileJobResolver struct {
	jobID     string
	status    string
	resultUrl string
}

func (r *FileJobResolver) JobId() string      { return r.jobID }
func (r *FileJobResolver) Status() string     { return r.status }
func (r *FileJobResolver) ResultUrl() *string { return &r.resultUrl }

// Input Struct
type ProcessFileInput struct {
	Type      string
	SourceKey string
	DestKey   string
	Width     *int32
	Height    *int32
}

func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}
