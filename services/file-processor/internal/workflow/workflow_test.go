package workflow

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetValidatedDimension_ReturnsDefaultForMissingKey(t *testing.T) {
	options := map[string]interface{}{}

	result, err := getValidatedDimension(options, "width", 800)

	assert.NoError(t, err)
	assert.Equal(t, 800, result)
}

func TestGetValidatedDimension_ReturnsDefaultForNilOptions(t *testing.T) {
	var options map[string]interface{}

	result, err := getValidatedDimension(options, "height", 600)

	assert.NoError(t, err)
	assert.Equal(t, 600, result)
}

func TestGetValidatedDimension_ParsesIntValue(t *testing.T) {
	options := map[string]interface{}{
		"width": 1024,
	}

	result, err := getValidatedDimension(options, "width", 800)

	assert.NoError(t, err)
	assert.Equal(t, 1024, result)
}

func TestGetValidatedDimension_ParsesFloat64Value(t *testing.T) {
	options := map[string]interface{}{
		"height": float64(768),
	}

	result, err := getValidatedDimension(options, "height", 600)

	assert.NoError(t, err)
	assert.Equal(t, 768, result)
}

func TestGetValidatedDimension_ErrorsOnInvalidType(t *testing.T) {
	options := map[string]interface{}{
		"width": "not-a-number",
	}

	_, err := getValidatedDimension(options, "width", 800)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid type")
}

func TestGetValidatedDimension_ErrorsOnNonPositive(t *testing.T) {
	options := map[string]interface{}{
		"width": 0,
	}

	_, err := getValidatedDimension(options, "width", 800)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "must be positive")

	options["width"] = -100
	_, err = getValidatedDimension(options, "width", 800)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "must be positive")
}

func TestGetValidatedDimension_ErrorsOnExceedingLimit(t *testing.T) {
	options := map[string]interface{}{
		"width": maxImageDimension + 1,
	}

	_, err := getValidatedDimension(options, "width", 800)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "exceeds maximum allowed dimension")
}

func TestProcessJob_StructFieldsAreAccessible(t *testing.T) {
	job := ProcessJob{
		ID:          "job-123",
		Type:        "resize",
		SourceKey:   "source/image.jpg",
		DestKey:     "dest/image.jpg",
		Options:     map[string]interface{}{"width": 100},
		CallbackURL: "http://callback.example.com",
	}

	assert.Equal(t, "job-123", job.ID)
	assert.Equal(t, "resize", job.Type)
	assert.Equal(t, "source/image.jpg", job.SourceKey)
	assert.Equal(t, "dest/image.jpg", job.DestKey)
	assert.Equal(t, 100, job.Options["width"])
	assert.Equal(t, "http://callback.example.com", job.CallbackURL)
}

func TestProcessResult_StructFieldsAreAccessible(t *testing.T) {
	result := ProcessResult{
		JobID:    "job-456",
		Success:  true,
		DestKey:  "result/image.jpg",
		Error:    "",
		Duration: 1500,
	}

	assert.Equal(t, "job-456", result.JobID)
	assert.True(t, result.Success)
	assert.Equal(t, "result/image.jpg", result.DestKey)
	assert.Empty(t, result.Error)
	assert.Equal(t, int64(1500), result.Duration)
}
