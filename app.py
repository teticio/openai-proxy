import boto3
import pandas as pd
import streamlit as st


@st.cache_data
def get_usage():
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(f"openai-usage")
    response = table.scan()
    items = response["Items"]
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    df = pd.DataFrame(items)
    return df


df = get_usage()

st.title("OpenAI usage")
staging = st.radio("Staging account", ["dev", "prod"])
df = df[df["staging"] == staging][df["model"] != "*"].drop(
    columns=["composite_key", "limit", "staging"]
)
df["user"] = df["user"].apply(lambda _: _.split("/")[-1])

dates = [_ for _ in df.columns if _.isnumeric()]
months = [f"{_[:2]}/20{_[-2:]}" for _ in dates]
month = st.selectbox("Month", months)
date = dates[months.index(month)]
del dates[months.index(month)]
df = df.drop(columns=dates).rename(columns={date: "usage"})

by = st.radio("Group by", ["user", "project"])
if by == "project":
    df = df[df["user"] == "*"].drop(columns=["user"]).set_index("project")
else:
    df = (
        df[df["user"] != "*"]
        .groupby(["user", "model"], as_index=False)
        .sum()
        .drop(columns=["project"])
        .set_index("user")
    )

df = df.pivot_table(
    index=df.index, columns="model", values="usage", aggfunc="sum", fill_value=0
).astype(float)

blue_hues_normalized = [
    (0.678, 0.847, 0.902),  # Sky Blue
    (0.529, 0.808, 0.922),  # Light Sky Blue
    (0.392, 0.584, 0.929),  # Dodger Blue
    (0.255, 0.412, 0.882),  # Royal Blue
    (0.118, 0.565, 1.000),  # Deep Sky Blue
    (0.000, 0.749, 1.000),  # Deep Sky Blue Darker
    (0.000, 0.502, 0.502),  # Steel Blue
    (0.282, 0.239, 0.545),  # Slate Blue
    (0.416, 0.353, 0.804),  # Medium Slate Blue
    (0.686, 0.933, 0.933),  # Light Blue
    (0.000, 0.749, 1.000),  # Medium Blue
    (0.000, 0.000, 0.804),  # Dark Blue
    (0.251, 0.878, 0.816),  # Pale Turquoise
    (0.275, 0.510, 0.706),  # Cadet Blue
    (0.000, 1.000, 1.000),  # Cyan or Aqua
    (0.498, 1.000, 1.000),  # Light Cyan
]

# Workaround bug with one column.
if len(df.columns) == 1:
    df.columns = df.columns.map(lambda _: _.replace(".", "dot"))
st.bar_chart(df, color=blue_hues_normalized[0  : len(df.columns)])
