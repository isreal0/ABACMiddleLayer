CREATE TABLE IF NOT EXISTS students (
    id SERIAL NOT NULL,
    stu_id VARCHAR(20) NOT NULL,
    name VARCHAR(45) NOT NULL,
    age INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

INSERT INTO students SELECT generate_series(1,100000) as key, (floor(random()*10^6))::integer, repeat(chr(int4(random()*26)+65),4), (random()*6^2)::integer;

