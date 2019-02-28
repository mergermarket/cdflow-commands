import hypothesis
import hypothesis.database

hypothesis.settings(database=hypothesis.database.ExampleDatabase(':memory:'))
