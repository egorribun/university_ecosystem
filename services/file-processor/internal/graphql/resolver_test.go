package graphql

import (
	"testing"

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

	args := struct{ ID string }{ID: "test-file-123"}
	result := resolver.File(args)

	assert.NotNil(t, result)
	assert.Equal(t, "test-file-123", result.ID())
	assert.Contains(t, result.URL(), "uploads")
	assert.Contains(t, result.URL(), "test-file-123")
}

func TestFileResolver_ID_ReturnsID(t *testing.T) {
	resolver := &FileResolver{
		id:  "file-abc",
		url: "http://example.com/file",
	}

	assert.Equal(t, "file-abc", resolver.ID())
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

	assert.Equal(t, "job-123", resolver.JobID())
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

func TestGenerateID_ReturnsNumericString(t *testing.T) {
	id := generateID()

	for _, char := range id {
		assert.True(t, char >= '0' && char <= '9', "ID should contain only digits")
	}
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
