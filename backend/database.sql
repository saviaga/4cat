-- jobs table
CREATE TABLE IF NOT EXISTS jobs (
  id          SERIAL PRIMARY KEY,
  jobtype     text    DEFAULT 'misc',
  remote_id   text,
  details     text,
  timestamp   integer,
  claim_after integer DEFAULT 0,
  claimed     integer DEFAULT 0
);

-- enforce
CREATE UNIQUE INDEX IF NOT EXISTS unique_job
  ON jobs (
    jobtype,
    remote_id
  );

-- threads
CREATE TABLE IF NOT EXISTS threads (
  id                 integer PRIMARY KEY, -- matches 4chan thread ID
  board              text,
  timestamp          integer DEFAULT 0, -- first known timestamp for this thread
  timestamp_scraped  integer, -- last timestamp this thread was scraped
  timestamp_modified integer, -- last timestamp this thread was modified (reported by 4chan)
  post_last          integer, -- ID of last post in this thread
  num_unique_ips     integer DEFAULT 0,
  num_replies        integer DEFAULT 0,
  num_images         integer DEFAULT 0,
  limit_bump         boolean DEFAULT FALSE,
  limit_image        boolean DEFAULT FALSE,
  is_sticky          boolean DEFAULT FALSE,
  is_closed          boolean DEFAULT FALSE,
  index_positions    text
);

CREATE INDEX IF NOT EXISTS threads_timestamp
  ON threads (
    timestamp
  );

-- posts
CREATE TABLE IF NOT EXISTS posts (
  id               integer PRIMARY KEY, -- matches 4chan post ID
  thread_id        integer,
  timestamp        integer,
  body             text,
  author           text,
  image_file       text,
  image_4chan      text,
  image_md5        text,
  image_dimensions text,
  image_filesize   integer,
  semantic_url     text,
  is_deleted       boolean DEFAULT FALSE,
  unsorted_data    text
);

CREATE INDEX IF NOT EXISTS posts_timestamp
  ON posts (
    timestamp
  );

CREATE INDEX IF NOT EXISTS posts_thread
  ON posts (
    thread_id
  );

-- post replies
CREATE TABLE IF NOT EXISTS posts_mention (
  post_id      integer,
  mentioned_id integer
);

CREATE INDEX IF NOT EXISTS mention_post
  ON posts_mention (
    post_id
  );

CREATE INDEX IF NOT EXISTS mention_mentioned
  ON posts_mention (
    mentioned_id
  );

TRUNCATE threads;
TRUNCATE posts;
TRUNCATE jobs;