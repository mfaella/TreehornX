struct Node {
    int value;
    struct Node *next;
};

void sll_unsafe_insert_back(struct Node **head, int key) {
    struct Node *x;
    struct Node *z;
    struct Node *w;

    z = malloc(sizeof(struct Node));
    z->value = key;

    x = *head;

    if(x != 0) {
        w = x->next;
        while(w != z) {
            x = w;
            w = w->next;
        }
        x->next = z;
    }

}