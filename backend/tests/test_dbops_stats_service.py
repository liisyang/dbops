from tests.test_dbops_asset_service import _FakeSession, _seed_asset_graph

from app.services.dbops_stats_service import DbopsStatsService


def test_stats_dashboard_counts_phase1_assets():
    db = _FakeSession()
    db.seed(*_seed_asset_graph())

    result = DbopsStatsService.dashboard(db)

    assert result["total_business_systems"] == 1
    assert result["total_clusters"] == 1
    assert result["total_instances"] == 1
    assert result["total_servers"] == 1
