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

func validProcessFileRequest(sourceKey, destKey string) *pb.ProcessFileRequest {
	return &pb.ProcessFileRequest{
		Id:        "object-key-validation",
		Type:      "image_resize",
		SourceKey: sourceKey,
		DestKey:   destKey,
	}
}
