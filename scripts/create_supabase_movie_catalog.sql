-- ==============================================================================
-- KINETO SUPABASE MIGRATION: CREATE CANONICAL MOVIE CATALOG TABLE
-- Run this in your Supabase Dashboard SQL Editor (takes ~5 seconds):
-- https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.movie_catalog (
    movie_key TEXT PRIMARY KEY,
    tmdb_id INTEGER,
    imdb_id TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    is_tv INTEGER DEFAULT 0,
    genres TEXT DEFAULT '',
    overview TEXT DEFAULT '',
    keywords TEXT DEFAULT '',
    director TEXT DEFAULT '',
    cinematographer TEXT DEFAULT '',
    composer TEXT DEFAULT '',
    screenwriter TEXT DEFAULT '',
    editor TEXT DEFAULT '',
    lead_actors TEXT DEFAULT '',
    studios TEXT DEFAULT '',
    poster TEXT DEFAULT '',
    vote_average REAL DEFAULT 0.0,
    vote_count INTEGER DEFAULT 0,
    embedding_json TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Fast Indexing for TMDB Lookups and Title/Year searches
CREATE INDEX IF NOT EXISTS idx_movie_catalog_tmdb_id ON public.movie_catalog(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_movie_catalog_title_year ON public.movie_catalog(title, year);

-- Enable RLS and allow unrestricted app access (same as lista/users/friends)
ALTER TABLE public.movie_catalog ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public all on movie_catalog" ON public.movie_catalog;
CREATE POLICY "Allow public all on movie_catalog" 
ON public.movie_catalog 
FOR ALL 
TO public 
USING (true) 
WITH CHECK (true);
