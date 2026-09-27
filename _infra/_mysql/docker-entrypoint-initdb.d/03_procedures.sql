-- stored procedure for granting an api permission to an api user.
-- creates the permission and the (active, firehose-style) user row when
-- missing, then links the two. idempotent.
USE playerdata;

DELIMITER //

DROP PROCEDURE IF EXISTS grant_api_permission //
CREATE PROCEDURE grant_api_permission (
    IN p_username VARCHAR(255),
    IN p_permission VARCHAR(255)
)
BEGIN
    INSERT INTO apiPermissions (permission)
    SELECT p_permission FROM DUAL
    WHERE NOT EXISTS (
        SELECT 1 FROM apiPermissions WHERE permission = p_permission
    );

    INSERT INTO apiUser (username, token, is_active)
    SELECT p_username, 'not-used-by-firehose', 1 FROM DUAL
    WHERE NOT EXISTS (
        SELECT 1 FROM apiUser WHERE username = p_username
    );

    INSERT INTO apiUserPerms (user_id, permission_id)
    SELECT u.id, perm.id
    FROM apiUser u
    JOIN apiPermissions perm ON perm.permission = p_permission
    WHERE u.username = p_username
        AND NOT EXISTS (
            SELECT 1 FROM apiUserPerms up
            WHERE up.user_id = u.id
                AND up.permission_id = perm.id
        );
END //

DELIMITER ;
