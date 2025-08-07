export const login = async (username: string, password: string) => {
  const response = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return await response.json();
};

export const getDeals = async (token: string) => {
  const response = await fetch("/api/deals", {
    headers: { "Authorization": `Bearer ${token}` },
  });
  return await response.json();
};
