package graphql

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/client"
)

func TestProcessFileRejectsUnimplementedTypesBeforeTemporal(t *testing.T) {
	for _, typ := range []string{"image_compress", "pdf_preview", "video_transcode", "image", "resize", ""} {
		t.Run(typ, func(t *testing.T) {
			started := false
			resolver := &Resolver{TemporalClient: &fakeTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
				started = true
				return &fakeWorkflowRun{id: "unexpected"}, nil
			}}}
			result, err := resolver.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{
				Input: ProcessFileInput{Type: typ, SourceKey: "in/file", DestKey: "out/file"},
			})
			require.Nil(t, result)
			require.ErrorContains(t, err, "unsupported file type")
			require.False(t, started, "unsupported jobs must not start Temporal workflows")
		})
	}
}

func TestProcessFileValidatesTypeAndKeysBeforeCapability(t *testing.T) {
	for _, test := range []struct {
		name, typ, source, dest, want string
	}{
		{name: "type first", typ: "pdf_preview", source: "../source", dest: "../dest", want: "unsupported file type"},
		{name: "source before destination", typ: "image_resize", source: "../source", dest: "../dest", want: "invalid source key"},
		{name: "destination before capability", typ: "image_resize", source: "src/a.png", dest: "../dest", want: "invalid destination key"},
		{name: "capability after valid inputs", typ: "image_resize", source: "src/a.png", dest: "dst/a.png", want: "file processing authorization required"},
	} {
		t.Run(test.name, func(t *testing.T) {
			resolver := &Resolver{RequireCapability: true}
			result, err := resolver.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{
				Input: ProcessFileInput{Type: test.typ, SourceKey: test.source, DestKey: test.dest},
			})
			require.Nil(t, result)
			require.ErrorContains(t, err, test.want)
		})
	}
}
