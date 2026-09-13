package jobcontract

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func validOptions() map[string]interface{} {
	return map[string]interface{}{"width": float64(100), "height": float64(100)}
}

func requireCode(t *testing.T, err error, code string) {
	t.Helper()
	var validationErr *ValidationError
	require.ErrorAs(t, err, &validationErr)
	require.NotNil(t, validationErr)
	require.Equal(t, code, validationErr.Code)
}

func TestValidateAcceptsCanonicalScalarJob(t *testing.T) {
	require.NoError(t, Validate("job-1", "image_resize", "input/a.png", "output/a.png", validOptions()))
}

func TestValidateRejectsIdentityAndType(t *testing.T) {
	tests := []struct {
		name string
		id   string
		typ  string
		code string
	}{
		{name: "missing id", typ: "image_resize", code: "missing_id"},
		{name: "long id", id: strings.Repeat("a", MaxIDLen+1), typ: "image_resize", code: "id_too_long"},
		{name: "unsupported type", id: "job", typ: "task", code: "unsupported_type"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			requireCode(t, Validate(test.id, test.typ, "in/a", "out/a", validOptions()), test.code)
		})
	}
}

func TestValidateRejectsUnsafeKeys(t *testing.T) {
	for _, test := range []struct {
		name string
		key  string
		code string
	}{
		{name: "missing", key: "", code: "missing_object_key"},
		{name: "long", key: strings.Repeat("a", MaxKeyLen+1), code: "object_key_too_long"},
		{name: "absolute", key: "/etc/passwd", code: "object_key_absolute"},
		{name: "windows absolute", key: `C:\\Windows\\file`, code: "object_key_absolute"},
		{name: "slash traversal", key: "a/../../secret", code: "object_key_traversal"},
		{name: "backslash traversal", key: `a\\..\\secret`, code: "object_key_traversal"},
		{name: "nul", key: "a\x00b", code: "object_key_nul"},
	} {
		t.Run(test.name, func(t *testing.T) {
			requireCode(t, Validate("job", "image_resize", test.key, "out/a", validOptions()), test.code)
		})
	}
}

func TestValidateRejectsOptionsOutsideScalarBoundaries(t *testing.T) {
	tests := []struct {
		name    string
		options map[string]interface{}
		code    string
	}{
		{name: "too many", options: func() map[string]interface{} {
			m := map[string]interface{}{}
			for i := 0; i <= MaxOptions; i++ {
				m[string(rune('a'+i))] = float64(1)
			}
			return m
		}(), code: "options_too_many"},
		{name: "empty key", options: map[string]interface{}{"": float64(1)}, code: "empty_option_key"},
		{name: "long key", options: map[string]interface{}{strings.Repeat("k", MaxOptionKeyLen+1): float64(1)}, code: "option_key_too_long"},
		{name: "null", options: map[string]interface{}{"width": nil}, code: "invalid_option_value"},
		{name: "nested", options: map[string]interface{}{"metadata": map[string]interface{}{"x": true}}, code: "invalid_option_value"},
		{name: "long string", options: map[string]interface{}{"width": strings.Repeat("1", MaxOptionValueLen+1)}, code: "invalid_option_value"},
		{name: "json number", options: map[string]interface{}{"width": json.Number("100")}, code: "__valid__"},
		{name: "long numeric stringer", options: map[string]interface{}{"width": json.Number(strings.Repeat("1", MaxOptionValueLen+1))}, code: "invalid_option_value"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := Validate("job", "image_resize", "in/a", "out/a", test.options)
			if test.code == "__valid__" {
				require.NoError(t, err)
				return
			}
			requireCode(t, err, test.code)
		})
	}
}

func TestValidationErrorIsSafeAndKeyCleaningIsBounded(t *testing.T) {
	err := &ValidationError{Code: "unsupported_type"}
	require.Equal(t, "invalid process job: unsupported_type", err.Error())
	// A value beginning with two dots is not a path segment but is still
	// rejected by the conservative normalized-key guard.
	requireCode(t, Validate("job", "image_resize", "....", "out/a", validOptions()), "object_key_traversal")
	requireCode(t, Validate("job", "image_resize", "in/a", "../out/a", validOptions()), "object_key_traversal")
	require.NoError(t, Validate("job", "image_resize", "in/a", "out/a", map[string]interface{}{
		"label":   "small",
		"enabled": true,
	}))
}
