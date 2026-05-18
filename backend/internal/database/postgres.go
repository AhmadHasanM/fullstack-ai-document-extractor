package database

import (
	"database/sql"
	"fmt"

	_ "github.com/lib/pq"
	"github.com/ahmadhasanm/ai-document-extractor/internal/models"
)

type Database struct {
	conn *sql.DB
}

func NewDatabase(connectionString string) (*Database, error) {
	db, err := sql.Open("postgres", connectionString)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Test connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// Set connection pool settings
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	database := &Database{conn: db}

	// Auto-create users table if it doesn't exist
	if err := database.ensureUsersTable(); err != nil {
		fmt.Printf("Warning: failed to ensure users table: %v\n", err)
	}

	return database, nil
}

func (db *Database) ensureUsersTable() error {
	query := `
		CREATE TABLE IF NOT EXISTS users (
			id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
			email VARCHAR(255) UNIQUE NOT NULL,
			password_hash VARCHAR(255) NOT NULL,
			name VARCHAR(255),
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, err := db.conn.Exec(query)
	return err
}

func (db *Database) Close() error {
	return db.conn.Close()
}

// Document operations
func (db *Database) CreateDocument(doc *models.Document) error {
	query := `
		INSERT INTO documents (id, filename, original_filename, file_path, file_size, status)
		VALUES ($1, $2, $3, $4, $5, $6)
	`
	_, err := db.conn.Exec(query, doc.ID, doc.Filename, doc.OriginalFilename, doc.FilePath, doc.FileSize, doc.Status)
	return err
}

func (db *Database) GetDocument(id string) (*models.Document, error) {
	query := `
		SELECT id, filename, original_filename, file_path, file_size, pdf_type, 
		       status, error_message, created_at, updated_at, processed_at
		FROM documents
		WHERE id = $1
	`
	
	doc := &models.Document{}
	err := db.conn.QueryRow(query, id).Scan(
		&doc.ID, &doc.Filename, &doc.OriginalFilename, &doc.FilePath, &doc.FileSize,
		&doc.PDFType, &doc.Status, &doc.ErrorMessage, &doc.CreatedAt, &doc.UpdatedAt, &doc.ProcessedAt,
	)
	
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("document not found")
	}
	
	return doc, err
}

func (db *Database) ListDocuments(limit, offset int) ([]models.Document, error) {
	query := `
		SELECT id, filename, original_filename, file_path, file_size, pdf_type, 
		       status, error_message, created_at, updated_at, processed_at
		FROM documents
		ORDER BY created_at DESC
		LIMIT $1 OFFSET $2
	`
	
	rows, err := db.conn.Query(query, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	
	var documents []models.Document
	for rows.Next() {
		var doc models.Document
		err := rows.Scan(
			&doc.ID, &doc.Filename, &doc.OriginalFilename, &doc.FilePath, &doc.FileSize,
			&doc.PDFType, &doc.Status, &doc.ErrorMessage, &doc.CreatedAt, &doc.UpdatedAt, &doc.ProcessedAt,
		)
		if err != nil {
			return nil, err
		}
		documents = append(documents, doc)
	}
	
	return documents, nil
}

func (db *Database) UpdateDocumentStatus(id, status string, errorMsg *string) error {
	query := `
		UPDATE documents
		SET status = $1, error_message = $2, updated_at = NOW()
		WHERE id = $3
	`
	_, err := db.conn.Exec(query, status, errorMsg, id)
	return err
}

func (db *Database) DeleteDocument(id string) error {
	query := `DELETE FROM documents WHERE id = $1`
	_, err := db.conn.Exec(query, id)
	return err
}

// Document Output operations
func (db *Database) GetDocumentOutput(documentID string) (*models.DocumentOutput, error) {
	query := `
		SELECT id, document_id, markdown_path, json_path, images_folder, created_at
		FROM document_outputs
		WHERE document_id = $1
	`
	
	output := &models.DocumentOutput{}
	err := db.conn.QueryRow(query, documentID).Scan(
		&output.ID, &output.DocumentID, &output.MarkdownPath, &output.JSONPath, &output.ImagesFolder, &output.CreatedAt,
	)
	
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("document output not found")
	}
	
	return output, err
}

// Queue operations
func (db *Database) CreateQueueItem(item *models.ProcessingQueue) error {
	query := `
		INSERT INTO processing_queue (id, document_id, priority, status)
		VALUES ($1, $2, $3, $4)
	`
	_, err := db.conn.Exec(query, item.ID, item.DocumentID, item.Priority, item.Status)
	return err
}

func (db *Database) GetQueueStatus(documentID string) (*models.ProcessingQueue, error) {
	query := `
		SELECT id, document_id, priority, status, retry_count, max_retries, 
		       error_message, created_at, started_at, completed_at
		FROM processing_queue
		WHERE document_id = $1
	`
	
	item := &models.ProcessingQueue{}
	err := db.conn.QueryRow(query, documentID).Scan(
		&item.ID, &item.DocumentID, &item.Priority, &item.Status, &item.RetryCount,
		&item.MaxRetries, &item.ErrorMessage, &item.CreatedAt, &item.StartedAt, &item.CompletedAt,
	)
	
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("queue item not found")
	}
	
	return item, err
}

// Chat operations
func (db *Database) SaveChatMessage(msg *models.ChatMessage) error {
	// Handle empty document_id as NULL (for chats without associated document)
	var docID interface{}
	if msg.DocumentID == "" {
		docID = nil
	} else {
		docID = msg.DocumentID
	}

	query := `
		INSERT INTO chat_history (id, document_id, session_id, role, message)
		VALUES ($1, $2, $3, $4, $5)
	`
	_, err := db.conn.Exec(query, msg.ID, docID, msg.SessionID, msg.Role, msg.Message)
	return err
}

func (db *Database) GetChatHistory(documentID, sessionID string, limit int) ([]models.ChatMessage, error) {
	// If sessionID is provided, use it; otherwise fall back to documentID
	var query string
	var rows *sql.Rows
	var err error

	if sessionID != "" {
		query = `
			SELECT id, document_id, session_id, role, message, created_at
			FROM chat_history
			WHERE session_id = $1
			ORDER BY created_at ASC
			LIMIT $2
		`
		rows, err = db.conn.Query(query, sessionID, limit)
	} else {
		query = `
			SELECT id, document_id, session_id, role, message, created_at
			FROM chat_history
			WHERE document_id = $1
			ORDER BY created_at ASC
			LIMIT $2
		`
		rows, err = db.conn.Query(query, documentID, limit)
	}

	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var messages []models.ChatMessage
	for rows.Next() {
		var msg models.ChatMessage
		err := rows.Scan(&msg.ID, &msg.DocumentID, &msg.SessionID, &msg.Role, &msg.Message, &msg.CreatedAt)
		if err != nil {
			return nil, err
		}
		messages = append(messages, msg)
	}

	return messages, nil
}

// Chunk operations
func (db *Database) GetDocumentChunks(documentID string) ([]models.DocumentChunk, error) {
	query := `
		SELECT id, document_id, chunk_index, content, page_number, chunk_type, metadata, created_at
		FROM document_chunks
		WHERE document_id = $1
		ORDER BY chunk_index
	`
	
	rows, err := db.conn.Query(query, documentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	
	var chunks []models.DocumentChunk
	for rows.Next() {
		var chunk models.DocumentChunk
		err := rows.Scan(
			&chunk.ID, &chunk.DocumentID, &chunk.ChunkIndex, &chunk.Content,
			&chunk.PageNumber, &chunk.ChunkType, &chunk.Metadata, &chunk.CreatedAt,
		)
		if err != nil {
			return nil, err
		}
		chunks = append(chunks, chunk)
	}
	
	return chunks, nil
}

// Chat session operations
func (db *Database) CreateChatSession(session *models.ChatSession) error {
	// Handle nil/empty document_id as NULL
	var docID interface{}
	if session.DocumentID != nil && *session.DocumentID != "" {
		docID = *session.DocumentID
	} else {
		docID = nil
	}

	query := `
		INSERT INTO chat_sessions (id, document_id, title)
		VALUES ($1, $2, $3)
	`
	_, err := db.conn.Exec(query, session.ID, docID, session.Title)
	return err
}

func (db *Database) GetChatSession(id string) (*models.ChatSession, error) {
	query := `
		SELECT id, document_id, title, created_at, updated_at
		FROM chat_sessions
		WHERE id = $1
	`

	session := &models.ChatSession{}
	var docID *string
	err := db.conn.QueryRow(query, id).Scan(
		&session.ID, &docID, &session.Title, &session.CreatedAt, &session.UpdatedAt,
	)
	session.DocumentID = docID

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("chat session not found")
	}

	return session, err
}

func (db *Database) ListChatSessions(limit, offset int) ([]models.ChatSession, error) {
	query := `
		SELECT id, document_id, title, created_at, updated_at
		FROM chat_sessions
		ORDER BY updated_at DESC
		LIMIT $1 OFFSET $2
	`

	rows, err := db.conn.Query(query, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var sessions []models.ChatSession
	for rows.Next() {
		var session models.ChatSession
		var docID *string
		err := rows.Scan(
			&session.ID, &docID, &session.Title, &session.CreatedAt, &session.UpdatedAt,
		)
		session.DocumentID = docID
		if err != nil {
			return nil, err
		}
		sessions = append(sessions, session)
	}

	return sessions, nil
}

func (db *Database) UpdateChatSession(id, title string) error {
	query := `
		UPDATE chat_sessions
		SET title = $1, updated_at = NOW()
		WHERE id = $2
	`
	_, err := db.conn.Exec(query, title, id)
	return err
}

func (db *Database) DeleteChatSession(id string) error {
	query := `DELETE FROM chat_sessions WHERE id = $1`
	_, err := db.conn.Exec(query, id)
	return err
}

// GetDocumentStatusCounts returns count of documents grouped by status.
// Tambahkan method ini ke file database.go yang sudah ada.
func (db *Database) GetDocumentStatusCounts() (map[string]int, error) {
	query := `
		SELECT status, COUNT(*) AS count
		FROM documents
		GROUP BY status
	`

	rows, err := db.conn.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	counts := map[string]int{
		"pending":    0,
		"processing": 0,
		"completed":  0,
		"failed":     0,
	}

	for rows.Next() {
		var status string
		var count int
		if err := rows.Scan(&status, &count); err != nil {
			return nil, err
		}
		counts[status] = count
	}

	return counts, rows.Err()
}

// User operations
func (db *Database) CreateUser(user *models.User) error {
	query := `
		INSERT INTO users (id, email, password_hash, name)
		VALUES ($1, $2, $3, $4)
	`
	_, err := db.conn.Exec(query, user.ID, user.Email, user.PasswordHash, user.Name)
	return err
}

func (db *Database) GetUserByEmail(email string) (*models.User, error) {
	query := `
		SELECT id, email, password_hash, name, created_at, updated_at
		FROM users
		WHERE email = $1
	`

	user := &models.User{}
	err := db.conn.QueryRow(query, email).Scan(
		&user.ID, &user.Email, &user.PasswordHash, &user.Name, &user.CreatedAt, &user.UpdatedAt,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("user not found")
	}

	return user, err
}

func (db *Database) GetUserByID(id string) (*models.User, error) {
	query := `
		SELECT id, email, password_hash, name, created_at, updated_at
		FROM users
		WHERE id = $1
	`

	user := &models.User{}
	err := db.conn.QueryRow(query, id).Scan(
		&user.ID, &user.Email, &user.PasswordHash, &user.Name, &user.CreatedAt, &user.UpdatedAt,
	)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("user not found")
	}

	return user, err
}