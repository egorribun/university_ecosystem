package objectkey

import (
	"errors"
	"strings"
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

func TestNormalize(t *testing.T) {
	tests := []struct {
		name string
		key  string
		want string
		err  error
	}{
		{name: "empty", key: "", err: ErrEmpty},
		{name: "too_long", key: strings.Repeat("a", MaxLength+1), err: ErrTooLong},
		{name: "nul", key: "a\x00b", err: ErrNUL},
		{name: "unix_absolute", key: "/etc/passwd", err: ErrAbsolute},
		{name: "windows_absolute", key: `C:\\Windows\\system32`, err: ErrAbsolute},
		{name: "backslash_rooted", key: `\\server\\share`, err: ErrAbsolute},
		{name: "dot_windows_root", key: `./\server\share`, err: ErrAbsolute},
		{name: "backslash_traversal", key: `a\\..\\secret`, err: ErrTraversal},
		{name: "slash_traversal", key: "a/../secret", err: ErrTraversal},
		{name: "dot_prefix", key: "....", err: ErrTraversal},
		{name: "canonicalized_absolute", key: "safe/../C:/Windows", err: ErrAbsolute},
		{name: "normalizes_separators", key: `tenant\\images\\photo.png`, want: "tenant/images/photo.png"},
		{name: "normalizes_dot_segments", key: "tenant/./images/photo.png", want: "tenant/images/photo.png"},
		{name: "colon_is_safe", key: "tenant:archive/object", want: "tenant:archive/object"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := Normalize(tc.key)
			if tc.err != nil {
				require.Error(t, err)
				require.True(t, errors.Is(err, tc.err))
				return
			}
			require.NoError(t, err)
			require.Equal(t, tc.want, got)
		})
	}
}
