-- Business rules that require checking more than one row or table.
BEGIN;

-- The creator is always a confirmed participant in their own plan.
CREATE FUNCTION add_plan_creator_participant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO plan_participant (plan_id, user_id, rsvp_status, responded_at)
    VALUES (NEW.plan_id, NEW.creator_id, 'accepted', now());
    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_creator_participant_ai
AFTER INSERT ON dining_plan
FOR EACH ROW EXECUTE FUNCTION add_plan_creator_participant();

CREATE FUNCTION keep_plan_creator() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.creator_id <> OLD.creator_id THEN
        RAISE EXCEPTION 'A plan creator cannot be changed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_creator_bu
BEFORE UPDATE OF creator_id ON dining_plan
FOR EACH ROW EXECUTE FUNCTION keep_plan_creator();

-- A plan may invite only its creator or a currently accepted friend of the creator.
CREATE FUNCTION check_plan_participant() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_creator_id bigint;
    v_new_invitation boolean;
BEGIN
    SELECT creator_id INTO v_creator_id
    FROM dining_plan
    WHERE plan_id = NEW.plan_id;

    IF v_creator_id IS NULL THEN
        RETURN NEW; -- The foreign key reports a missing plan.
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_new_invitation := true;
    ELSE
        v_new_invitation := NEW.plan_id IS DISTINCT FROM OLD.plan_id
                            OR NEW.user_id IS DISTINCT FROM OLD.user_id;
    END IF;

    IF NEW.user_id = v_creator_id THEN
        IF NEW.rsvp_status <> 'accepted' THEN
            RAISE EXCEPTION 'The plan creator must remain an accepted participant';
        END IF;
    ELSIF v_new_invitation AND NOT EXISTS (
        SELECT 1 FROM friendship f
        WHERE f.status = 'accepted'
          AND ((f.requester_id = v_creator_id AND f.addressee_id = NEW.user_id)
            OR (f.addressee_id = v_creator_id AND f.requester_id = NEW.user_id))
    ) THEN
        RAISE EXCEPTION 'Plan invitees must be accepted friends of the creator';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.rsvp_status = 'accepted' AND NEW.rsvp_status <> 'accepted'
           AND EXISTS (
               SELECT 1 FROM plan_vote
               WHERE plan_id = OLD.plan_id AND user_id = OLD.user_id
           ) THEN
            RAISE EXCEPTION 'A participant with a vote cannot decline before removing the vote';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_participant_biu
BEFORE INSERT OR UPDATE OF plan_id, user_id, rsvp_status ON plan_participant
FOR EACH ROW EXECUTE FUNCTION check_plan_participant();

CREATE FUNCTION keep_creator_participation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- During a plan delete the parent row is already gone; cascading is allowed.
    IF EXISTS (
        SELECT 1 FROM dining_plan p
        WHERE p.plan_id = OLD.plan_id AND p.creator_id = OLD.user_id
    ) THEN
        RAISE EXCEPTION 'A plan creator cannot be removed from participants';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER plan_participant_creator_bd
BEFORE DELETE ON plan_participant
FOR EACH ROW EXECUTE FUNCTION keep_creator_participation();

-- A participant can vote only while the plan is open and before its deadline.
-- The composite foreign keys also enforce membership and candidate choice.
CREATE FUNCTION check_plan_vote() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
    v_deadline timestamptz;
    v_rsvp text;
BEGIN
    SELECT status, voting_deadline INTO v_status, v_deadline
    FROM dining_plan
    WHERE plan_id = NEW.plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN NEW; -- The foreign key reports a missing plan.
    END IF;

    IF v_status <> 'open' OR statement_timestamp() >= v_deadline THEN
        RAISE EXCEPTION 'Voting is closed for plan %', NEW.plan_id;
    END IF;

    SELECT rsvp_status INTO v_rsvp
    FROM plan_participant
    WHERE plan_id = NEW.plan_id AND user_id = NEW.user_id
    FOR UPDATE;

    IF v_rsvp IS DISTINCT FROM 'accepted' THEN
        RAISE EXCEPTION 'Only accepted participants may vote';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_vote_biu
BEFORE INSERT OR UPDATE ON plan_vote
FOR EACH ROW EXECUTE FUNCTION check_plan_vote();

CREATE FUNCTION check_vote_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
    v_deadline timestamptz;
BEGIN
    SELECT status, voting_deadline INTO v_status, v_deadline
    FROM dining_plan
    WHERE plan_id = OLD.plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN OLD; -- Cascading deletion of the whole plan.
    END IF;

    IF v_status <> 'open' OR statement_timestamp() >= v_deadline THEN
        RAISE EXCEPTION 'Votes cannot be removed after voting closes';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER plan_vote_bd
BEFORE DELETE ON plan_vote
FOR EACH ROW EXECUTE FUNCTION check_vote_delete();

CREATE FUNCTION check_candidate_write() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
    v_deadline timestamptz;
BEGIN
    SELECT status, voting_deadline INTO v_status, v_deadline
    FROM dining_plan
    WHERE plan_id = NEW.plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN NEW; -- The foreign key reports a missing plan.
    END IF;

    IF v_status <> 'draft'
       AND (v_status <> 'open' OR statement_timestamp() >= v_deadline) THEN
        RAISE EXCEPTION 'Candidates may only be added before voting closes';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_candidate_biu
BEFORE INSERT OR UPDATE ON plan_candidate
FOR EACH ROW EXECUTE FUNCTION check_candidate_write();

CREATE FUNCTION check_candidate_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
    v_deadline timestamptz;
BEGIN
    SELECT status, voting_deadline INTO v_status, v_deadline
    FROM dining_plan
    WHERE plan_id = OLD.plan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN OLD; -- Cascading deletion of the whole plan.
    END IF;

    IF v_status NOT IN ('draft', 'open')
       OR (v_status = 'open' AND statement_timestamp() >= v_deadline)
       OR EXISTS (
           SELECT 1 FROM plan_vote
           WHERE plan_id = OLD.plan_id AND restaurant_id = OLD.restaurant_id
       ) THEN
        RAISE EXCEPTION 'A closed, chosen or voted-for candidate cannot be removed';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER plan_candidate_bd
BEFORE DELETE ON plan_candidate
FOR EACH ROW EXECUTE FUNCTION check_candidate_delete();

-- Recommendations are sent to accepted friends; old recommendations remain
-- as history even if the friendship later ends.
CREATE FUNCTION check_recommendation_friendship() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1
    FROM friendship f
    WHERE f.status = 'accepted'
      AND ((f.requester_id = NEW.sender_id AND f.addressee_id = NEW.receiver_id)
        OR (f.addressee_id = NEW.sender_id AND f.requester_id = NEW.receiver_id))
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Recommendations may only be sent to accepted friends';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER recommendation_friendship_biu
BEFORE INSERT OR UPDATE OF sender_id, receiver_id ON recommendation
FOR EACH ROW EXECUTE FUNCTION check_recommendation_friendship();

-- If a visit resulted from a plan, it must be at that plan's final restaurant.
CREATE FUNCTION check_visit_origin() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_status text;
    v_chosen_restaurant_id bigint;
BEGIN
    IF NEW.plan_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT status, chosen_restaurant_id
      INTO v_status, v_chosen_restaurant_id
    FROM dining_plan
    WHERE plan_id = NEW.plan_id
    FOR SHARE;

    IF NOT FOUND THEN
        RETURN NEW; -- The foreign key reports a missing plan.
    END IF;

    IF v_status <> 'finalized' OR v_chosen_restaurant_id <> NEW.restaurant_id THEN
        RAISE EXCEPTION 'A plan-originated visit must use the finalized restaurant';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER visit_origin_biu
BEFORE INSERT OR UPDATE OF plan_id, restaurant_id ON visit
FOR EACH ROW EXECUTE FUNCTION check_visit_origin();

-- Once finalized, a plan's final restaurant cannot change underneath visits.
CREATE FUNCTION keep_finalized_plan_choice() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'finalized'
       AND (NEW.status IS DISTINCT FROM OLD.status
         OR NEW.chosen_restaurant_id IS DISTINCT FROM OLD.chosen_restaurant_id) THEN
        RAISE EXCEPTION 'A finalized plan cannot change status or restaurant';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER finalized_plan_bu
BEFORE UPDATE OF status, chosen_restaurant_id ON dining_plan
FOR EACH ROW EXECUTE FUNCTION keep_finalized_plan_choice();

COMMIT;
