package service

import (
	"testing"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestValidateProcessFileRequestRejectsWindowsDriveKeys(t *testing.T) {
	driveKeys := []struct {
		name string
		key  string
	}{
		{name: "backslash_absolute", key: `C:\Windows\system32\drivers\etc\hosts`},
		{name: "slash_absolute", key: "C:/Windows/system32/drivers/etc/hosts"},
		{name: "drive_relative", key: "C:tenant/object"},
		{name: "lowercase_drive_relative", key: "z:tenant/object"},
	}

	for _, tc := range driveKeys {
		t.Run(tc.name+"/source", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest(tc.key, "output/result.png"))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "absolute path")
		})
		t.Run(tc.name+"/destination", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest("input/source.png", tc.key))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "absolute path")
		})
	}
}

func TestValidateProcessFileRequestAcceptsNonDriveColonKey(t *testing.T) {
	err := validateProcessFileRequest(validProcessFileRequest(
		"tenant:archive/object",
		"output/result.png",
	))

	require.NoError(t, err)
}

func TestValidateProcessFileRequestRejectsBackslashTraversal(t *testing.T) {
	for _, key := range []string{`a\..\secret`, `a\\..\\secret`} {
		t.Run(key+"/source", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest(key, "output/result.png"))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "path traversal")
		})
		t.Run(key+"/destination", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest("input/source.png", key))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "path traversal")
		})
	}
}

func TestValidateProcessFileKeyRejectsSharedBoundaryErrors(t *testing.T) {
	for _, tc := range []struct {
		name         string
		key          string
		wantContains string
	}{
		{name: "empty", key: "", wantContains: "must not be empty"},
		{name: "nul", key: "a\x00b", wantContains: "contains NUL"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := validateProcessFileKey(tc.key)
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, tc.wantContains)
		})
	}
}

func TestValidateProcessFileRequestRejectsCanonicalizedAbsoluteKeys(t *testing.T) {
	keys := []struct {
		name string
		key  string
	}{
		{name: "dot_drive_absolute", key: "./C:/Windows/system32"},
		{name: "collapsed_drive_absolute", key: "safe/../C:/Windows/system32"},
		{name: "dot_windows_root", key: `./\server\share`},
	}

	for _, tc := range keys {
		t.Run(tc.name+"/source", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest(tc.key, "output/result.png"))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "absolute path")
		})
		t.Run(tc.name+"/destination", func(t *testing.T) {
			err := validateProcessFileRequest(validProcessFileRequest("input/source.png", tc.key))
			require.Error(t, err)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "absolute path")
		})
	}
}

func TestValidateProcessFileRequestAcceptsCanonicalizedNonDriveColonKey(t *testing.T) {
	err := validateProcessFileRequest(validProcessFileRequest(
		"./tenant:archive/object",
		"output/result.png",
	))

	require.NoError(t, err)
}

func validProcessFileRequest(sourceKey, destKey string) *pb.ProcessFileRequest {
	return &pb.ProcessFileRequest{
		Id:        "object-key-validation",
		Type:      "image_resize",
		SourceKey: sourceKey,
		DestKey:   destKey,
	}
}
