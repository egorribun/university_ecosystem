package hub

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

// maxChatAudienceMembers matches the backend chat group size bound. A larger
// authorization list is malformed and must not fall back to legacy delivery.
const maxChatAudienceMembers = 100

// shouldRefreshMissingAudienceCheckpoint reports whether a legacy event with no
// audience can be recovered from current authorized chat/message REST state.
// Require the event type in both trusted envelope locations to agree so a
// mismatched or malformed frame never triggers a cache refresh.
func shouldRefreshMissingAudienceCheckpoint(envelopeType, payloadType string) bool {
	if envelopeType == "" || envelopeType != payloadType {
		return false
	}
	switch envelopeType {
	case "new_message", "message_edited", "message_deleted", "reaction_changed", "read":
		return true
	default:
		return false
	}
}

// decodeChatAudience reads only the reserved top-level audience property.
// Missing is the legacy room-wide contract; an explicit empty array is a
// present policy that allows nobody. Null, aliases, duplicate keys/IDs and
// malformed IDs fail closed.
func decodeChatAudience(data []byte) (map[string]struct{}, bool, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return nil, false, fmt.Errorf("chat envelope is not a JSON object")
	}

	rawAudience, audiencePresent, err := readChatAudienceField(decoder)
	if err != nil {
		return nil, false, err
	}
	if !audiencePresent {
		return nil, false, nil
	}

	return decodeChatAudienceMembers(rawAudience)
}

func readChatAudienceField(decoder *json.Decoder) (json.RawMessage, bool, error) {
	var rawAudience json.RawMessage
	audiencePresent := false
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return nil, audiencePresent, fmt.Errorf("read chat envelope key: %w", err)
		}
		// Token returns strings for keys while the decoder is inside an object;
		// malformed non-string keys are rejected by Token itself.
		key := token.(string)

		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return nil, audiencePresent, fmt.Errorf("read chat envelope value: %w", err)
		}
		if !strings.EqualFold(key, "audience") {
			continue
		}
		if key != "audience" {
			return nil, audiencePresent, fmt.Errorf("chat audience key is not canonical")
		}
		if audiencePresent {
			return nil, audiencePresent, fmt.Errorf("chat audience key is duplicated")
		}
		rawAudience = value
		audiencePresent = true
	}

	token, err := decoder.Token()
	if err != nil || token != json.Delim('}') {
		return nil, audiencePresent, fmt.Errorf("chat envelope object is incomplete")
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, audiencePresent, fmt.Errorf("chat envelope has trailing JSON")
		}
		return nil, audiencePresent, fmt.Errorf("read trailing chat envelope data: %w", err)
	}
	return rawAudience, audiencePresent, nil
}

func decodeChatAudienceMembers(rawAudience json.RawMessage) (map[string]struct{}, bool, error) {
	trimmed := bytes.TrimSpace(rawAudience)
	if len(trimmed) == 0 || trimmed[0] != '[' {
		return nil, true, fmt.Errorf("chat audience must be an array")
	}
	arrayDecoder := json.NewDecoder(bytes.NewReader(trimmed))
	allowed, err := decodeChatAudienceArray(arrayDecoder)
	return allowed, true, err
}

func decodeChatAudienceArray(arrayDecoder *json.Decoder) (map[string]struct{}, error) {
	token, err := arrayDecoder.Token()
	if err != nil || token != json.Delim('[') {
		return nil, fmt.Errorf("chat audience is not a JSON array")
	}
	allowed := make(map[string]struct{})
	for arrayDecoder.More() {
		if len(allowed) >= maxChatAudienceMembers {
			return nil, fmt.Errorf("chat audience exceeds %d members", maxChatAudienceMembers)
		}
		var userID string
		if err := arrayDecoder.Decode(&userID); err != nil {
			return nil, fmt.Errorf("decode chat audience member: %w", err)
		}
		if !isCanonicalAudienceUUID(userID) {
			return nil, fmt.Errorf("chat audience contains a non-canonical user ID")
		}
		if _, duplicate := allowed[userID]; duplicate {
			return nil, fmt.Errorf("chat audience contains a duplicate user ID")
		}
		allowed[userID] = struct{}{}
	}
	token, err = arrayDecoder.Token()
	if err != nil || token != json.Delim(']') {
		return nil, fmt.Errorf("chat audience array is incomplete")
	}
	var trailing json.RawMessage
	if err := arrayDecoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("chat audience has trailing JSON")
		}
		return nil, fmt.Errorf("read trailing chat audience data: %w", err)
	}
	return allowed, nil
}

func isCanonicalAudienceUUID(value string) bool {
	if len(value) != 36 {
		return false
	}
	for index := 0; index < len(value); index++ {
		if index == 8 || index == 13 || index == 18 || index == 23 {
			if value[index] != '-' {
				return false
			}
			continue
		}
		if !isLowerHexASCII(value[index]) {
			return false
		}
	}
	return true
}

func isLowerHexASCII(character byte) bool {
	return '0' <= character && character <= '9' || 'a' <= character && character <= 'f'
}
