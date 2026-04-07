-- Add job description (plain text, HTML stripped) to jobs table
-- Run in Supabase SQL Editor after 010_add_multi_label_clusters.sql

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT;
