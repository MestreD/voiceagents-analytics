-- Worked example for the staging layer. The other two staging models follow
-- the same shape, so use this one as the template.
--
-- A staging model does four things and nothing else:
--   1. reads exactly one source
--   2. renames columns to the project's conventions
--   3. casts types
--   4. turns flags into booleans and leaves derived metrics alone
--
-- No joins, no aggregation, no business logic. Those belong downstream, so
-- that there is one obvious place to look when a number is wrong.

with source as (

    select * from {{ source('raw', 'calls') }}

),

renamed as (

    select
        -- identifiers
        call_id,
        gestoria_id,

        -- timestamps
        started_at::timestamp                             as started_at,
        (started_at::timestamp
            + (duration_seconds * interval 1 second))     as ended_at,

        -- attributes
        detected_intent,
        language                                          as language_code,

        -- measures
        duration_seconds,
        duration_seconds / 60.0                           as duration_minutes,

        -- flags: the source ships 0/1 integers, downstream wants booleans
        was_resolved = 1                                  as is_resolved,
        transferred_to_human = 1                          as is_transferred_to_human,

        -- pseudonymous caller identifier, kept so repeat callers can be
        -- counted without holding a phone number
        caller_hash

    from source

)

select * from renamed
