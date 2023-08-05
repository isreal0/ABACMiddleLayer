
# Copyright (c) 2021-2023, PostgreSQL Global Development Group

# Test behavior with different schema on subscriber
use strict;
use warnings;
use PostgreSQL::Test::Cluster;
use PostgreSQL::Test::Utils;
use Test::More;

# Create publisher node
my $node_publisher = PostgreSQL::Test::Cluster->new('publisher');
$node_publisher->init(allows_streaming => 'logical');
$node_publisher->start;

# Create subscriber node
my $node_subscriber = PostgreSQL::Test::Cluster->new('subscriber');
$node_subscriber->init(allows_streaming => 'logical');
$node_subscriber->start;

# Create some preexisting content on publisher
$node_publisher->safe_psql('postgres',
	"CREATE TABLE test_tab (a int primary key, b varchar)");
$node_publisher->safe_psql('postgres',
	"INSERT INTO test_tab VALUES (1, 'foo'), (2, 'bar')");

# Setup structure on subscriber
$node_subscriber->safe_psql('postgres',
	"CREATE TABLE test_tab (a int primary key, b text, c timestamptz DEFAULT now(), d bigint DEFAULT 999, e int GENERATED BY DEFAULT AS IDENTITY)"
);

# Setup logical replication
my $publisher_connstr = $node_publisher->connstr . ' dbname=postgres';
$node_publisher->safe_psql('postgres',
	"CREATE PUBLICATION tap_pub FOR ALL TABLES");

$node_subscriber->safe_psql('postgres',
	"CREATE SUBSCRIPTION tap_sub CONNECTION '$publisher_connstr' PUBLICATION tap_pub"
);

# Wait for initial table sync to finish
$node_subscriber->wait_for_subscription_sync($node_publisher, 'tap_sub');

my $result =
  $node_subscriber->safe_psql('postgres',
	"SELECT count(*), count(c), count(d = 999) FROM test_tab");
is($result, qq(2|2|2), 'check initial data was copied to subscriber');

# Update the rows on the publisher and check the additional columns on
# subscriber didn't change
$node_publisher->safe_psql('postgres', "UPDATE test_tab SET b = encode(sha256(b::bytea), 'hex')");

$node_publisher->wait_for_catchup('tap_sub');

$result =
  $node_subscriber->safe_psql('postgres',
	"SELECT count(*), count(c), count(d = 999), count(e) FROM test_tab");
is($result, qq(2|2|2|2),
	'check extra columns contain local defaults after copy');

# Change the local values of the extra columns on the subscriber,
# update publisher, and check that subscriber retains the expected
# values
$node_subscriber->safe_psql('postgres',
	"UPDATE test_tab SET c = 'epoch'::timestamptz + 987654321 * interval '1s'"
);
$node_publisher->safe_psql('postgres',
	"UPDATE test_tab SET b = encode(sha256(a::text::bytea), 'hex')");

$node_publisher->wait_for_catchup('tap_sub');

$result = $node_subscriber->safe_psql('postgres',
	"SELECT count(*), count(extract(epoch from c) = 987654321), count(d = 999) FROM test_tab"
);
is($result, qq(2|2|2), 'check extra columns contain locally changed data');

# Another insert
$node_publisher->safe_psql('postgres',
	"INSERT INTO test_tab VALUES (3, 'baz')");

$node_publisher->wait_for_catchup('tap_sub');

$result =
  $node_subscriber->safe_psql('postgres',
	"SELECT count(*), count(c), count(d = 999), count(e) FROM test_tab");
is($result, qq(3|3|3|3),
	'check extra columns contain local defaults after apply');


# Check a bug about adding a replica identity column on the subscriber
# that was not yet mapped to a column on the publisher.  This would
# result in errors on the subscriber and replication thus not
# progressing.
# (https://www.postgresql.org/message-id/flat/a9139c29-7ddd-973b-aa7f-71fed9c38d75%40minerva.info)

$node_publisher->safe_psql('postgres', "CREATE TABLE test_tab2 (a int)");

$node_subscriber->safe_psql('postgres', "CREATE TABLE test_tab2 (a int)");

$node_subscriber->safe_psql('postgres',
	"ALTER SUBSCRIPTION tap_sub REFRESH PUBLICATION");

$node_subscriber->wait_for_subscription_sync;

# Add replica identity column.  (The serial is not necessary, but it's
# a convenient way to get a default on the new column so that rows
# from the publisher that don't have the column yet can be inserted.)
$node_subscriber->safe_psql('postgres',
	"ALTER TABLE test_tab2 ADD COLUMN b serial PRIMARY KEY");

$node_publisher->safe_psql('postgres', "INSERT INTO test_tab2 VALUES (1)");

$node_publisher->wait_for_catchup('tap_sub');

is( $node_subscriber->safe_psql(
		'postgres', "SELECT count(*), min(a), max(a) FROM test_tab2"),
	qq(1|1|1),
	'check replicated inserts on subscriber');


$node_subscriber->stop;
$node_publisher->stop;

done_testing();
