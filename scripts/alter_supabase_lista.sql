-- ==============================================================================
-- KINETO SUPABASE MIGRATION: ADD SEASON & TMDB_ID TO LISTA
-- Run this in your Supabase Dashboard SQL Editor (takes ~2 seconds):
-- https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql
-- ==============================================================================

ALTER TABLE public.lista ADD COLUMN IF NOT EXISTS season INTEGER DEFAULT NULL;
ALTER TABLE public.lista ADD COLUMN IF NOT EXISTS tmdb_id INTEGER DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_lista_tmdb_id ON public.lista(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_lista_parent_tmdb ON public.lista(parent_id, tmdb_id);
