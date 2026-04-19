"""Unique fixtures for data generation."""


def unique_subject(unique, C="CA", ST="QC", L="Montreal", O="Tarameteo", OU="PKI", CN=None):  # noqa: E741
    if CN is None:
        CN = unique("text")

    return f"/C={C}/ST={ST}/L={L}/O={O}/OU={OU}/CN={CN}"
