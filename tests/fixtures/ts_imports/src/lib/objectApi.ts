function helper() {
  return 1;
}

export function archive(id: string) {
  return id;
}

export const objectApi = {
  reject: async (id: string) => id,
  archive,
  refresh() {
    return helper();
  },
};
