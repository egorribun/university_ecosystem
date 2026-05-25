package graphql

import (
	"testing"

	gql "github.com/graph-gophers/graphql-go"
	"github.com/stretchr/testify/assert"
)

func TestResolver_Health_ReturnsOK(t *testing.T) {
	resolver := &Resolver{
		MinioBucket: "test-bucket",
	}

	result := resolver.Health()

	assert.Equal(t, "OK", result)
}

func TestResolver_File_ReturnsFileResolver(t *testing.T) {
	resolver := &Resolver{
		MinioBucket: "uploads",
	}

	// W140 (z) #1: args.ID is gql.ID (not string) per schema `file(id: ID!)`.
	args := struct{ ID gql.ID }{ID: gql.ID("test-file-123")}
	result := resolver.File(args)

	assert.NotNil(t, result)
	assert.Equal(t, gql.ID("test-file-123"), result.ID())
	assert.Contains(t, result.URL(), "uploads")
	assert.Contains(t, result.URL(), "test-file-123")
}

func TestFileResolver_ID_ReturnsID(t *testing.T) {
	resolver := &FileResolver{
		id:  "file-abc",
		url: "http://example.com/file",
	}

	// W140 (z) #1: return type is gql.ID (not string).
	assert.Equal(t, gql.ID("file-abc"), resolver.ID())
}

func TestFileResolver_URL_ReturnsURL(t *testing.T) {
	resolver := &FileResolver{
		id:  "file-abc",
		url: "http://example.com/file",
	}

	assert.Equal(t, "http://example.com/file", resolver.URL())
}

func TestFileResolver_Size_ReturnsPointer(t *testing.T) {
	resolver := &FileResolver{}

	size := resolver.Size()

	assert.NotNil(t, size)
	assert.Equal(t, int32(0), *size)
}

func TestFileResolver_Type_ReturnsUnknown(t *testing.T) {
	resolver := &FileResolver{}

	fileType := resolver.Type()

	assert.NotNil(t, fileType)
	assert.Equal(t, "unknown", *fileType)
}

func TestFileJobResolver_JobId_ReturnsJobID(t *testing.T) {
	resolver := &FileJobResolver{
		jobID:     "job-123",
		status:    "RUNNING",
		resultURL: "http://result.com",
	}

	// W140 (z) #1: return type is gql.ID (not string) per schema FileJob.jobId ID!.
	assert.Equal(t, gql.ID("job-123"), resolver.JobID())
}

func TestFileJobResolver_Status_ReturnsStatus(t *testing.T) {
	resolver := &FileJobResolver{
		jobID:     "job-123",
		status:    "COMPLETED",
		resultURL: "",
	}

	assert.Equal(t, "COMPLETED", resolver.Status())
}

func TestFileJobResolver_ResultUrl_ReturnsPointer(t *testing.T) {
	resolver := &FileJobResolver{
		jobID:     "job-123",
		status:    "COMPLETED",
		resultURL: "http://result.com/file.jpg",
	}

	url := resolver.ResultURL()

	assert.NotNil(t, url)
	assert.Equal(t, "http://result.com/file.jpg", *url)
}

func TestGenerateID_ReturnsNonEmptyString(t *testing.T) {
	id := generateID()

	assert.NotEmpty(t, id)
}

// TD-33-11: generateID now returns "file-process-<uuid>" format (RZ-W19-17).
func TestGenerateID_ReturnsPrefixedUUID(t *testing.T) {
	id := generateID()

	assert.True(t, len(id) > len("file-process-"), "ID should be longer than prefix")
	assert.Contains(t, id, "file-process-")
	// UUID portion: 36 chars of hex digits and dashes
	uuidPart := id[len("file-process-"):]
	assert.Regexp(t, `^[0-9a-f-]{36}$`, uuidPart)
}

func TestProcessFileInput_FieldsAccessible(t *testing.T) {
	width := int32(800)
	height := int32(600)

	input := ProcessFileInput{
		Type:      "resize",
		SourceKey: "source/image.jpg",
		DestKey:   "dest/image.jpg",
		Width:     &width,
		Height:    &height,
	}

	assert.Equal(t, "resize", input.Type)
	assert.Equal(t, "source/image.jpg", input.SourceKey)
	assert.Equal(t, "dest/image.jpg", input.DestKey)
	assert.Equal(t, int32(800), *input.Width)
	assert.Equal(t, int32(600), *input.Height)
}

func TestProcessFileInput_NilDimensions(t *testing.T) {
	input := ProcessFileInput{
		Type:      "optimize",
		SourceKey: "file.jpg",
		DestKey:   "out.jpg",
		Width:     nil,
		Height:    nil,
	}

	assert.Nil(t, input.Width)
	assert.Nil(t, input.Height)
}
