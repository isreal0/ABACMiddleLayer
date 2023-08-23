DO $$
DECLARE 
	user_amount int := 10000;
BEGIN
	FOR i IN 1..user_amount LOOP
		EXECUTE format('CREATE USER user%s;', i);
	END LOOP;
END;
$$;
