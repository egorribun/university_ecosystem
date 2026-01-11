package graphql

import (
	"context"
	"fmt"
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

func (r *Resolver) File(args struct{ ID string }) *FileResolver {
	return &FileResolver{
		id:  args.ID,
		url: fmt.Sprintf("http://localhost:9000/%s/%s", r.MinioBucket, args.ID),
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

	job := workflow.ProcessJob{
		ID:        generateID(),
		Type:      args.Input.Type,
		SourceKey: args.Input.SourceKey,
		DestKey:   args.Input.DestKey,
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
