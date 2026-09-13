package objectkey

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestIsAbsolute(t *testing.T) {
	tests := []struct {
		name string
		key  string
		want bool
	}{
		{name: "empty", key: "", want: false},
		{name: "single_segment", key: "a", want: false},
		{name: "unix_absolute", key: "/etc/passwd", want: true},
		{name: "windows_rooted", key: `\server\share`, want: true},
		{name: "uppercase_drive_backslashes", key: `C:\Windows\system32`, want: true},
		{name: "uppercase_drive_slashes", key: "C:/Windows/system32", want: true},
		{name: "uppercase_drive_relative", key: "C:tenant/object", want: true},
		{name: "lowercase_drive_relative", key: "z:tenant/object", want: true},
		{name: "non_drive_colon", key: "tenant:archive/object", want: false},
		{name: "numeric_prefix_colon", key: "1:archive/object", want: false},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			require.Equal(t, tc.want, IsAbsolute(tc.key))
		})
	}
}
