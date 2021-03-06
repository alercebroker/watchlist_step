from apf.core.step import GenericStep
import logging
from typing import Any, List, Tuple
from db_plugins.db.sql.models import Detection
from db_plugins.db.sql import SQLConnection
import datetime
BASE_RADIUS=30/3600

class WatchlistStep(GenericStep):
    """WatchlistStep Description

    Parameters
    ----------
    consumer : GenericConsumer
        Description of parameter `consumer`.
    **step_args : type
        Other args passed to step (DB connections, API requests, etc.)

    """

    def __init__(
        self,
        consumer=None,
        alerts_db_connection: SQLConnection = None,
        users_db_connection: SQLConnection = None,
        config=None,
        level=logging.INFO,
        **step_args,
    ):
        super().__init__(consumer, config=config, level=level)
        self.alerts_db_connection = alerts_db_connection or SQLConnection()
        self.alerts_db_connection.connect(config["alert_db_config"]["SQL"])
        self.users_db_connection = users_db_connection or SQLConnection()
        self.users_db_connection.connect(config["users_db_config"]["SQL"])

    def execute(self, messages: list):
        candids = [message["candid"] for message in messages]
        coordinates = self.get_coordinates(candids)
        matches = self.match_user_targets(coordinates)
        if len(matches) > 0:
            self.insert_matches(matches)

    def get_coordinates(self, candids: List[int]) -> List[Tuple]:
        radecs = (
            self.alerts_db_connection.query(
                Detection.ra, Detection.dec, Detection.oid, Detection.candid
            )
            .filter(Detection.candid.in_(candids))
            .all()
        )
        return radecs

    def match_user_targets(self, coordinates: List[Tuple]) -> List[Tuple]:
        str_values = ",\n".join(
            [f"({val[0]}, {val[1]}, '{val[2]}', '{val[3]}')" for val in coordinates]
        )
        query = (
        f"""
            WITH positions (ra, dec, oid, candid) AS (
                    VALUES
                    %s
            )
            SELECT
            positions.oid,
            positions.candid,
            watchlist_target.id
            FROM watchlist_target, positions
            WHERE q3c_join(positions.ra, positions.dec,watchlist_target.ra, watchlist_target.dec, {BASE_RADIUS})
            AND q3c_dist(positions.ra, positions.dec, watchlist_target.ra, watchlist_target.dec) < watchlist_target.radius
        """
            % str_values
        )
        res = self.users_db_connection.session.execute(query).fetchall()
        return res

    def insert_matches(self, matches: List[Tuple]):
        str_values = ",\n".join(
            [
                f"({val[2]}, '{val[0]}', '{val[1]}', '{datetime.datetime.now()}')"
                for val in matches
            ]
        )
        query = (
            """
        INSERT INTO watchlist_match (target_id, object_id, candid, date) VALUES %s;
        """
            % str_values
        )
        self.users_db_connection.session.execute(query)
        self.users_db_connection.session.commit()
