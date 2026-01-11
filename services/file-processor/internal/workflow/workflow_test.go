package workflow

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetIntOption_ReturnsDefaultForMissingKey(t *testing.T) {
	options := map[string]interface{}{}

	result := getIntOption(options, "width", 800)

	assert.Equal(t, 800, result)
}

func TestGetIntOption_ReturnsDefaultForNilOptions(t *testing.T) {
	var options map[string]interface{}

	result := getIntOption(options, "height", 600)

	assert.Equal(t, 600, result)
}

func TestGetIntOption_ParsesIntValue(t *testing.T) {
	options := map[string]interface{}{
		"width": 1024,
	}

	result := getIntOption(options, "width", 800)

	assert.Equal(t, 1024, result)
}

func TestGetIntOption_ParsesFloat64Value(t *testing.T) {
	options := map[string]interface{}{
		"height": float64(768),
	}

	result := getIntOption(options, "height", 600)

	assert.Equal(t, 768, result)
}

func TestGetIntOption_ParsesInt32Value(t *testing.T) {
	options := map[string]interface{}{
		"quality": int32(85),
	}

	result := getIntOption(options, "quality", 75)

	assert.Equal(t, 85, result)
}

func TestGetIntOption_ParsesInt64Value(t *testing.T) {
	options := map[string]interface{}{
		"maxSize": int64(1000000),
	}

	result := getIntOption(options, "maxSize", 500000)

	assert.Equal(t, 1000000, result)
}

func TestGetIntOption_ReturnsDefaultForUnsupportedType(t *testing.T) {
	options := map[string]interface{}{
		"width": "not-a-number",
	}

	result := getIntOption(options, "width", 800)

	assert.Equal(t, 800, result)
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
