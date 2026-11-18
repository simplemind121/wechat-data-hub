CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS wdh_vectors_v1;
CREATE TABLE IF NOT EXISTS wdh_vectors_v1.chunks (
  workspace_id uuid NOT NULL,
  result_id uuid NOT NULL,
  message_id uuid NOT NULL,
  chunk_index integer NOT NULL,
  model_version text NOT NULL,
  start_offset integer NOT NULL,
  end_offset integer NOT NULL,
  body_text text NOT NULL,
  embedding public.vector(512) NOT NULL,
  PRIMARY KEY (result_id, chunk_index),
  FOREIGN KEY (workspace_id, result_id) REFERENCES public.processing_results(workspace_id, id),
  FOREIGN KEY (workspace_id, message_id) REFERENCES public.messages(workspace_id, id),
  CHECK (start_offset >= 0 AND end_offset > start_offset)
);
CREATE INDEX IF NOT EXISTS ix_vector_workspace_model ON wdh_vectors_v1.chunks(workspace_id, model_version);
CREATE INDEX IF NOT EXISTS ix_vector_hnsw ON wdh_vectors_v1.chunks USING hnsw (embedding public.vector_cosine_ops);
