# Flow Diagrams: Client → Main Service → RabbitMQ → AI Service

## 🔄 Overall Flow (Text/Image Input)

```
Client              Main Service         RabbitMQ            AI Service                      AWS Services
  │                     │                    │                    │                                │
  │  1. Send Request    │                    │                    │                                │
  ├────────────────────►│                    │                    │                                │
  │  (text or image)    │                    │                    │                                │
  │                     │                    │                    │                                │
  │                     │  2. Publish Msg    │                    │                                │
  │                     ├───────────────────►│                    │                                │
  │                     │  correlation_id    │                    │                                │
  │                     │  reply_to queue    │                    │                                │
  │                     │                    │                    │                                │
  │                     │                    │  3. Route to Worker│                                │
  │                     │                    ├───────────────────►│                                │
  │                     │                    │                    │                                │
  │                     │                    │                    │  4. Process Pipeline:          │
  │                     │                    │                    ├───────────────────────────────►│
  │                     │                    │                    │                                │
  │                     │                    │                    │  • Guardrails (input check)    │
  │                     │                    │                    │  • Claude LLM/Vision           │
  │                     │                    │                    │  • RAG Knowledge Base          │
  │                     │                    │                    │◄───────────────────────────────┤
  │                     │                    │                    │                                │
  │                     │                    │                    │  Local Services:               │
  │                     │                    │                    │  • OntologyService             │
  │                     │                    │                    │    (ingredient KB)             │
  │                     │                    │                    │  • ConflictDetection           │
  │                     │                    │                    │    (check conflicts)           │
  │                     │                    │                    │  • SuggestionService           │
  │                     │                    │                    │    (co-occurrence)             │
  │                     │                    │                    │  • ValidationService           │
  │                     │                    │                    │    (validate data)             │
  │                     │                    │                    │                                │
  │                     │                    │  5. Publish Result │                                │
  │                     │                    │◄───────────────────┤                                │
  │                     │                    │  (to reply_to)     │                                │
  │                     │                    │                    │                                │
  │                     │  6. Consume Result │                    │                                │
  │                     │◄───────────────────┤                    │                                │
  │                     │  (match corr_id)   │                    │                                │
  │                     │                    │                    │                                │
  │  7. Return Response │                    │                    │                                │
  │◄────────────────────┤                    │                    │                                │
  │  {dish, cart, ...}  │                    │                    │                                │
  │                     │                    │                    │                                │
  ▼                     ▼                    ▼                    ▼                                ▼
```

---

## 📸 Detailed Image Processing Flow

```
Client         Main Service         AWS S3          RabbitMQ        AI Service         AWS Bedrock
  │                 │                  │                │                │                  │
  │ 1. Upload       │                  │                │                │                  │
  │    Image 🖼️     │                  │                │                │                  │
  ├────────────────►│                  │                │                │                  │
  │                 │                  │                │                │                  │
  │                 │  2. Upload to S3 │                │                │                  │
  │                 ├─────────────────►│                │                │                  │
  │                 │  (uuid.webp)     │                │                │                  │
  │                 │                  │                │                │                  │
  │                 │  3. S3 Key       │                │                │                  │
  │                 │◄─────────────────┤                │                │                  │
  │                 │  abc123.webp     │                │                │                  │
  │                 │                  │                │                │                  │
  │                 │  4. Publish Msg  │                │                │                  │
  │                 ├─────────────────────────────────► │                │                  │
  │                 │  {               │                │                │                  │
  │                 │   s3_url: abc123,│                │                │                  │
  │                 │   corr_id: uuid  │                │                │                  │
  │                 │  }               │                │                │                  │
  │                 │                  │                │                │                  │
  │                 │                  │                │  5. Consume    │                  │
  │                 │                  │                ├───────────────►│                  │
  │                 │                  │                │                │                  │
  │                 │                  │  6. Download   │                │                  │
  │                 │                  │◄───────────────┤                │                  │
  │                 │                  │  Image         │                │                  │
  │                 │                  │────────────────►│               │                  │
  │                 │                  │                │  7. Base64     │                  │
  │                 │                  │                │                │                  │
  │                 │                  │                │  8. Vision API │                  │
  │                 │                  │                ├─────────────────────────────────► │
  │                 │                  │                │  Multimodal    │                  │
  │                 │                  │                │  Prompt        │                  │
  │                 │                  │                │                │                  │
  │                 │                  │                │  9. Extract    │                  │
  │                 │                  │                │◄───────────────────────────────── ┤
  │                 │                  │                │  dish_name     │                  │
  │                 │                  │                │  ingredients   │                  │
  │                 │                  │                │                │                  │
  │                 │                  │                │ 10. Get Recipe │                  │
  │                 │                  │                ├─────────────────────────────────► │
  │                 │                  │                │  (RAG KB)      │                  │
  │                 │                  │                │◄───────────────────────────────── ┤
  │                 │                  │                │                │                  │
  │                 │                  │                │ 11. Process Pipeline:             │
  │                 │                  │                │  Local Services:                  │
  │                 │                  │                │  • OntologyService                │
  │                 │                  │                │    (ingredient KB)                │
  │                 │                  │                │  • ConflictDetection              │
  │                 │                  │                │    (check conflicts)              │
  │                 │                  │                │  • SuggestionService              │
  │                 │                  │                │    (co-occurrence)                │
  │                 │                  │                │  • ValidationService              │
  │                 │                  │                │    (validate data)                │
  │                 │                  │                │                │                  │
  │                 │                  │ 12. Publish    │                │                  │
  │                 │                  │    Result      │                │                  │
  │                 │  13. Consume     │◄───────────────┤                │                  │
  │                 │◄───────────────────────────────── ┤                │                  │
  │                 │  {               │                │                │                  │
  │                 │   dish,          │                │                │                  │
  │                 │   cart,          │                │                │                  │
  │                 │   excluded_items │                │                │                  │
  │                 │  }               │                │                │                  │
  │                 │                  │                │                │                  │
  │ 14. Response    │                  │                │                │                  │
  │◄────────────────┤                  │                │                │                  │
  │                 │                  │                │                │                  │
  ▼                 ▼                  ▼                ▼                ▼                  ▼
```

---

## 📝 Processing Details

### Text Input
```
"Tôi muốn nấu phở nhưng dị ứng đậu phộng"
    ↓
Claude LLM Extract:
    dish_name: "Phở bò"
    excluded_ingredients: [{"name": "Đậu phộng", "reason": "dị ứng"}]
    ↓
Get Recipe from KB
    ↓
Filter: Remove "Đậu phộng" from recipe
    ↓
Response with excluded_ingredients details
```

### Image Input
```
Image Upload → S3 → AI Service
    ↓
Download from S3 + Convert to Base64
    ↓
Claude Vision:
    "Identify dish and ingredients in this image..."
    ↓
Same processing as text input
```

---

## 🔑 Key Points

### RabbitMQ Pattern
- **Pattern**: RPC (Request-Reply)
- **correlation_id**: Match request với response
- **reply_to**: Temporary queue cho response
- **TTL**: 5 minutes
- **Timeout**: 100 seconds

### AI Service Processing
1. **Guardrails Check** (Input safety)
2. **Claude LLM/Vision** (Extract information)
3. **RAG Knowledge Base** (Get recipe)
4. **Fuzzy Matching** (Resolve ingredients)
5. **Filter Excluded Items** (Remove allergies)
6. **Conflict Detection** (Safety warnings)
7. **Suggestions** (Complementary items)
8. **Guardrails Check** (Output validation)

### Image Processing Special Steps
- S3 Upload (Main Service → AWS S3)
- S3 Download (AI Service ← AWS S3)
- Base64 Encoding
- Multimodal Prompt (Image + Text)
- Claude Vision API

---

## 📊 Timing

| Step | Text Input | Image Input |
|------|-----------|-------------|
| Main Service | 0.5s | 2s (S3 upload) |
| RabbitMQ | 0.1s | 0.1s |
| AI Service | 15-25s | 25-35s (+ S3 download) |
| **Total** | **15-26s** | **27-37s** |

---

## 🔒 Security

- **AWS Guardrails**: PII, content policy, topic policy
- **Input Validation**: Pydantic schemas
- **Image Validation**: Format, size, dimensions
- **S3 Security**: Bucket policies, IAM roles
- **RabbitMQ**: Message TTL, DLQ for failures
