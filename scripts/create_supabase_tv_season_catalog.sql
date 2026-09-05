-- ==============================================================================
-- KINETO SUPABASE MIGRATION: CREATE CANONICAL TV SEASON CATALOG TABLE
-- Run this in your Supabase Dashboard SQL Editor (takes ~3 seconds):
-- https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.tv_season_catalog (
    season_key TEXT PRIMARY KEY,               -- e.g. '203857_s1', '203857_s3'
    tmdb_id INTEGER NOT NULL,                  -- TMDB Show ID
    season_number INTEGER NOT NULL,            -- Season number (1, 2, 3...)
    show_title TEXT NOT NULL,                  -- Main show title
    season_name TEXT DEFAULT '',               -- e.g. 'Night Country', 'Season 3'
    air_date TEXT DEFAULT '',                  -- Season premiere date (YYYY-MM-DD)
    year INTEGER,                              -- Release year of this season
    overview TEXT DEFAULT '',                  -- Season-specific synopsis
    poster TEXT DEFAULT '',                    -- Season-specific poster URL
    vote_average REAL DEFAULT 0.0,             -- Season rating
    episode_count INTEGER DEFAULT 0,           -- Number of episodes in season
    director TEXT DEFAULT '',                  -- Season directors / showrunner
    lead_actors TEXT DEFAULT '',               -- Season-specific cast
    cinematographer TEXT DEFAULT '',
    composer TEXT DEFAULT '',
    screenwriter TEXT DEFAULT '',
    embedding_json TEXT DEFAULT '',            -- 384D FastEmbed semantic vector
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Fast Indexes for TMDB lookup, season matching, and title search
CREATE UNIQUE INDEX IF NOT EXISTS idx_tv_season_tmdb_season ON public.tv_season_catalog(tmdb_id, season_number);
CREATE INDEX IF NOT EXISTS idx_tv_season_show_title ON public.tv_season_catalog(show_title);

-- Enable RLS and allow unrestricted app access (same as movie_catalog/lista)
ALTER TABLE public.tv_season_catalog ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public all on tv_season_catalog" ON public.tv_season_catalog;
CREATE POLICY "Allow public all on tv_season_catalog" 
ON public.tv_season_catalog 
FOR ALL 
TO public 
USING (true) 
WITH CHECK (true);
