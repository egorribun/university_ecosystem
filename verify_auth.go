package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"

	v1 "github.com/authzed/authzed-go/proto/authzed/api/v1"
	"github.com/authzed/authzed-go/v1"
	"github.com/authzed/grpcutil"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	spicedbEndpoint = "127.0.0.1:50051"
	presharedKey    = "university-secret-key"
)

func main() {
	// Debug TCP
	conn, err := net.Dial("tcp", spicedbEndpoint)
	if err != nil {
		log.Fatalf("TCP Connect failed: %v", err)
	}
	conn.Close()
	fmt.Println("✅ TCP connection established")

	// Connect to SpiceDB
	client, err := authzed.NewClient(
		spicedbEndpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpcutil.WithInsecureBearerToken(presharedKey),
	)
	if err != nil {
		log.Fatalf("Failed to connect to SpiceDB: %v", err)
	}

	ctx := context.Background()

	// 1. Write Schema
	schema, _ := os.ReadFile("schema.zed") // Assume in same dir
	_, err = client.SchemaServiceClient.WriteSchema(ctx, &v1.WriteSchemaRequest{
		Schema: string(schema),
	})
	if err != nil {
		log.Fatalf("Failed to write schema: %v", err)
	}
	fmt.Println("✅ Schema written successfully")

	// 2. Write Relationships (User 'alice' owns document 'doc1')
	_, err = client.PermissionsServiceClient.WriteRelationships(ctx, &v1.WriteRelationshipsRequest{
		Updates: []*v1.RelationshipUpdate{
			{
				Operation: v1.RelationshipUpdate_OPERATION_TOUCH,
				Relationship: &v1.Relationship{
					Resource: &v1.ObjectReference{
						ObjectType: "document",
						ObjectId:   "doc1",
					},
					Relation: "owner",
					Subject: &v1.SubjectReference{
						Object: &v1.ObjectReference{
							ObjectType: "user",
							ObjectId:   "alice",
						},
					},
				},
			},
		},
	})
	if err != nil {
		log.Fatalf("Failed to write relationship: %v", err)
	}
	fmt.Println("✅ Relationship written: alice owns doc1")

	// 3. Check Permission (Can alice view doc1?)
	resp, err := client.PermissionsServiceClient.CheckPermission(ctx, &v1.CheckPermissionRequest{
		Resource: &v1.ObjectReference{
			ObjectType: "document",
			ObjectId:   "doc1",
		},
		Permission: "view",
		Subject: &v1.SubjectReference{
			Object: &v1.ObjectReference{
				ObjectType: "user",
				ObjectId:   "alice",
			},
		},
	})
	if err != nil {
		log.Fatalf("Check permission failed: %v", err)
	}

	if resp.Permissionship == v1.CheckPermissionResponse_PERMISSIONSHIP_HAS_PERMISSION {
		fmt.Println("✅ Check passed: alice can view doc1")
	} else {
		log.Fatalf("❌ Check failed: alice cannot view doc1")
	}
}
