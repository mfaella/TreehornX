
struct Node {
    int data;
    struct Node *next;
};

void sll_sorted_first_lt_last(struct Node *root) {
    struct Node *tmp;
    int first_data;
    int last_data;
    if (!root) {
        return;
    }
    first_data = root->data;
    tmp = root->next;
    if (!tmp) {
        return;
    }
    while(root) {
        tmp = root;
        root = root->next;
    }
    last_data = tmp->data;
    if (first_data >= last_data) {
        first_data = root->data;
    }
}
