// cuts the list after the first node with data > key
struct Node {
    int data;
    struct Node *next;
};

void sll_safe_shape_split(struct Node *root) {
    int key;
    int d;
    struct Node *cur;

    cur = root;
    while (cur) {
        d = cur->data;
        if (d > key) {
            cur->next = NULL;
            break;
        }
        cur = cur->next;
    }
}
